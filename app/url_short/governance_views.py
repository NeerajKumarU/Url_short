from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AbuseReportForm, ApprovalReviewForm, WorkspaceGovernanceForm
from .governance import review_approval, submit_campaign_for_approval, submit_link_for_approval
from .models import AbuseReport, ApprovalRequest, Campaign, WorkspaceMembership, urlModel
from .permissions import (
    platform_admin_required,
    require_link_access,
    require_workspace_role,
)
from .selectors import get_current_workspace
from .services import record_audit
from .notifications import send_notification


@login_required
@require_POST
def link_submit_approval(request, pk):
    link = get_object_or_404(urlModel.objects.select_related("workspace"), pk=pk)
    require_link_access(request.user, link, WorkspaceMembership.Role.EDITOR)
    try:
        approval, created = submit_link_for_approval(
            link,
            request.user,
            request.POST.get("comment", ""),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        if created:
            record_audit(
                action="APPROVAL_REQUESTED",
                actor=request.user,
                workspace=link.workspace,
                target=link,
            )
            messages.success(request, "Link submitted for approval.")
            admin_emails = link.workspace.memberships.filter(
                is_active=True,
                role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.ADMIN),
                user__email__gt="",
            ).values_list("user__email", flat=True)
            for email in admin_emails:
                send_notification(
                    event_type="APPROVAL_REQUIRED",
                    recipient=email,
                    subject=f"Approval required for /{link.shorturl}",
                    body=f"{request.user.username} submitted /{link.shorturl} for review in {link.workspace.name}.",
                    workspace=link.workspace,
                )
        else:
            messages.info(request, "This link already has a pending approval request.")
    return redirect("dashboard")


@login_required
@require_POST
def campaign_submit_approval(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.EDITOR)
    campaign = get_object_or_404(Campaign, pk=pk, workspace=workspace)
    approval, created = submit_campaign_for_approval(
        campaign,
        request.user,
        request.POST.get("comment", ""),
    )
    if created:
        record_audit(
            action="APPROVAL_REQUESTED",
            actor=request.user,
            workspace=workspace,
            target=campaign,
        )
        messages.success(request, "Campaign submitted for approval.")
    else:
        messages.info(request, "This campaign already has a pending approval request.")
    return redirect("campaign_list")


@login_required
def approval_list(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    approvals = workspace.approval_requests.select_related(
        "requester", "reviewer", "link", "campaign"
    )
    return render(
        request,
        "governance/approvals.html",
        {"workspace": workspace, "approvals": approvals, "review_form": ApprovalReviewForm()},
    )


@login_required
@require_POST
def approval_review(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    approval = get_object_or_404(ApprovalRequest, pk=pk, workspace=workspace)
    form = ApprovalReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose Approve or Reject before submitting.")
        return redirect("approval_list")
    approve = form.cleaned_data["decision"] == "approve"
    try:
        review_approval(
            approval,
            request.user,
            approve=approve,
            comment=form.cleaned_data["comment"],
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        action = "APPROVAL_GRANTED" if approve else "APPROVAL_REJECTED"
        record_audit(
            action=action,
            actor=request.user,
            workspace=workspace,
            target=approval.target,
        )
        messages.success(request, "Approval decision recorded.")
        if approval.requester.email:
            send_notification(
                event_type="APPROVAL_RESULT",
                recipient=approval.requester.email,
                subject=f"Approval {approval.get_status_display().lower()}",
                body=f"Your request for {approval.target} was {approval.get_status_display().lower()}.",
                workspace=workspace,
            )
    return redirect("approval_list")


@login_required
def workspace_governance_settings(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    form = WorkspaceGovernanceForm(request.POST or None, instance=workspace)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(
            action="WORKSPACE_GOVERNANCE_UPDATED",
            actor=request.user,
            workspace=workspace,
            target=workspace,
            metadata={"require_link_approval": workspace.require_link_approval},
        )
        messages.success(request, "Governance settings updated.")
        return redirect("workspace_governance_settings")
    return render(
        request,
        "governance/settings.html",
        {"workspace": workspace, "form": form},
    )


def report_link(request, shorturl):
    link = get_object_or_404(urlModel, shorturl=shorturl)
    form = AbuseReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.link = link
        report.reporter = request.user if request.user.is_authenticated else None
        report.save()
        record_audit(
            action="LINK_REPORTED",
            actor=request.user if request.user.is_authenticated else None,
            workspace=link.workspace,
            target=link,
            metadata={"reason": report.reason, "report_id": report.pk},
        )
        for email in get_user_model().objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True):
            send_notification(
                event_type="LINK_REPORTED",
                recipient=email,
                subject=f"Link reported: /{link.shorturl}",
                body=f"A {report.get_reason_display().lower()} report was submitted for /{link.shorturl}.",
                workspace=link.workspace,
            )
        return render(request, "governance/report_received.html", {"link": link})
    return render(request, "governance/report_form.html", {"link": link, "form": form})


@platform_admin_required
def platform_report_list(request):
    reports = AbuseReport.objects.select_related("link__owner", "reporter", "resolved_by")
    return render(request, "admin_dashboard/reports.html", {"reports": reports})


@platform_admin_required
@require_POST
def platform_report_action(request, pk):
    report = get_object_or_404(AbuseReport.objects.select_related("link"), pk=pk)
    action = request.POST.get("action")
    if action not in {"review", "dismiss", "disable"}:
        messages.error(request, "Unknown report action.")
        return redirect("platform_report_list")
    if action == "review":
        report.status = AbuseReport.Status.UNDER_REVIEW
    elif action == "dismiss":
        report.status = AbuseReport.Status.DISMISSED
    else:
        report.status = AbuseReport.Status.ACTIONED
        report.link.is_enabled = False
        report.link.approval_status = urlModel.ApprovalStatus.DISABLED
        report.link.save(update_fields=("is_enabled", "approval_status", "updated_at"))
    report.resolved_by = request.user
    report.resolution = request.POST.get("resolution", "").strip()[:2000]
    report.resolved_at = timezone.now() if action in {"dismiss", "disable"} else None
    report.save(update_fields=("status", "resolved_by", "resolution", "resolved_at"))
    record_audit(
        action="REPORT_ACTIONED" if action == "disable" else "REPORT_UPDATED",
        actor=request.user,
        workspace=report.link.workspace,
        target=report.link,
        metadata={"report_id": report.pk, "action": action},
    )
    messages.success(request, "Report workflow updated.")
    return redirect("platform_report_list")
