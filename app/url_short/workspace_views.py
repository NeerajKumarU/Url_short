from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CampaignForm
from .models import AuditLog, Campaign, Workspace, WorkspaceMembership
from .permissions import require_workspace_role
from .selectors import campaigns_for_workspace, get_current_workspace
from .services import record_audit


@login_required
def workspace_list(request):
    memberships = request.user.workspace_memberships.select_related("workspace").filter(
        is_active=True,
        workspace__is_active=True,
    )
    return render(
        request,
        "workspaces/list.html",
        {"memberships": memberships, "workspace": get_current_workspace(request)},
    )


@login_required
@require_POST
def switch_workspace(request, slug):
    membership = get_object_or_404(
        WorkspaceMembership.objects.select_related("workspace"),
        user=request.user,
        workspace__slug=slug,
        workspace__is_active=True,
        is_active=True,
    )
    request.session["workspace_id"] = membership.workspace_id
    messages.success(request, f"Switched to {membership.workspace.name}.")
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("dashboard")


@login_required
def campaign_list(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    campaigns = campaigns_for_workspace(workspace).annotate(
        link_count=Count("links", distinct=True),
        click_count=Coalesce(Sum("links__count"), 0),
        conversion_count=Count("conversions", distinct=True),
    )
    return render(
        request,
        "campaigns/list.html",
        {"workspace": workspace, "campaigns": campaigns},
    )


@login_required
def campaign_create(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.EDITOR)
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.workspace = workspace
        campaign.created_by = request.user
        campaign.save()
        record_audit(
            action="CAMPAIGN_CREATED",
            actor=request.user,
            workspace=workspace,
            target=campaign,
            metadata={"name": campaign.name},
        )
        messages.success(request, f"Campaign “{campaign.name}” was created.")
        return redirect("campaign_list")
    return render(
        request,
        "campaigns/form.html",
        {"form": form, "workspace": workspace, "page_title": "Create campaign"},
    )


@login_required
def campaign_edit(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.EDITOR)
    campaign = get_object_or_404(Campaign, pk=pk, workspace=workspace)
    form = CampaignForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(
            action="CAMPAIGN_UPDATED",
            actor=request.user,
            workspace=workspace,
            target=campaign,
            metadata={"name": campaign.name},
        )
        messages.success(request, f"Campaign “{campaign.name}” was updated.")
        return redirect("campaign_list")
    return render(
        request,
        "campaigns/form.html",
        {
            "form": form,
            "workspace": workspace,
            "campaign": campaign,
            "page_title": "Edit campaign",
        },
    )


@login_required
def workspace_audit_log(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    logs = AuditLog.objects.filter(workspace=workspace).select_related("actor")[:200]
    return render(
        request,
        "workspaces/audit_log.html",
        {"workspace": workspace, "logs": logs},
    )


@login_required
def account_settings(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    membership = request.user.workspace_memberships.filter(
        workspace=workspace,
        is_active=True,
    ).first()
    return render(
        request,
        "account/settings.html",
        {"workspace": workspace, "membership": membership},
    )
