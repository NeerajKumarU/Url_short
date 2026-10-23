from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CustomDomainForm, RedirectRuleForm, UtmBuilderForm
from .integrations import dns_verification_provider
from .link_services import create_link_version, rollback_link
from .models import CustomDomain, LinkVersion, RedirectRule, WorkspaceMembership, urlModel
from .permissions import require_link_access, require_workspace_role
from .selectors import get_current_workspace
from .services import record_audit


@login_required
def custom_domain_list(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    return render(
        request,
        "domains/list.html",
        {"workspace": workspace, "domains": workspace.custom_domains.all()},
    )


@login_required
def custom_domain_create(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    form = CustomDomainForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        domain = form.save(commit=False)
        domain.workspace = workspace
        try:
            with transaction.atomic():
                if domain.is_default:
                    CustomDomain.objects.filter(workspace=workspace, is_default=True).update(
                        is_default=False
                    )
                domain.save()
        except IntegrityError:
            form.add_error("domain", "This domain has already been claimed.")
        else:
            record_audit(
                action="DOMAIN_ADDED",
                actor=request.user,
                workspace=workspace,
                target=domain,
                metadata={"domain": domain.domain},
            )
            messages.success(request, "Domain added in Pending state. DNS has not been verified yet.")
            return redirect("custom_domain_list")
    return render(
        request,
        "domains/form.html",
        {"workspace": workspace, "form": form},
    )


@login_required
@require_POST
def custom_domain_verify(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    domain = get_object_or_404(CustomDomain, pk=pk, workspace=workspace)
    result = dns_verification_provider.verify_txt(domain)
    record_audit(
        action="DOMAIN_VERIFICATION_REQUESTED",
        actor=request.user,
        workspace=workspace,
        target=domain,
        metadata={"provider_available": result.available},
    )
    if not result.available:
        messages.warning(request, result.detail)
    elif result.verified:
        messages.success(request, "DNS verification succeeded.")
    else:
        messages.error(request, result.detail)
    return redirect("custom_domain_list")


def _managed_link(request, pk, minimum_role):
    link = get_object_or_404(urlModel.objects.select_related("workspace"), pk=pk)
    require_link_access(request.user, link, minimum_role)
    return link


@login_required
def routing_rule_list(request, link_pk):
    link = _managed_link(request, link_pk, WorkspaceMembership.Role.VIEWER)
    return render(
        request,
        "routing/list.html",
        {"link": link, "rules": link.routing_rules.all()},
    )


@login_required
def routing_rule_create(request, link_pk):
    link = _managed_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    form = RedirectRuleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        rule = form.save(commit=False)
        rule.link = link
        rule.save()
        create_link_version(link, request.user, f"Routing rule added: {rule.name}")
        record_audit(
            action="ROUTING_RULE_CREATED",
            actor=request.user,
            workspace=link.workspace,
            target=rule,
            metadata={"link": link.shorturl, "condition": rule.condition_type},
        )
        messages.success(request, "Routing rule created.")
        return redirect("routing_rule_list", link_pk=link.pk)
    return render(request, "routing/form.html", {"link": link, "form": form, "title": "Add rule"})


@login_required
def routing_rule_edit(request, link_pk, pk):
    link = _managed_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    rule = get_object_or_404(RedirectRule, pk=pk, link=link)
    form = RedirectRuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        form.save()
        create_link_version(link, request.user, f"Routing rule updated: {rule.name}")
        record_audit(
            action="ROUTING_RULE_UPDATED",
            actor=request.user,
            workspace=link.workspace,
            target=rule,
            metadata={"link": link.shorturl},
        )
        messages.success(request, "Routing rule updated.")
        return redirect("routing_rule_list", link_pk=link.pk)
    return render(request, "routing/form.html", {"link": link, "form": form, "title": "Edit rule"})


@login_required
@require_POST
def routing_rule_delete(request, link_pk, pk):
    link = _managed_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    rule = get_object_or_404(RedirectRule, pk=pk, link=link)
    name = rule.name
    rule.delete()
    create_link_version(link, request.user, f"Routing rule deleted: {name}")
    record_audit(
        action="ROUTING_RULE_DELETED",
        actor=request.user,
        workspace=link.workspace,
        target=link,
        metadata={"rule_name": name},
    )
    messages.success(request, "Routing rule deleted.")
    return redirect("routing_rule_list", link_pk=link.pk)


@login_required
def link_version_list(request, link_pk):
    link = _managed_link(request, link_pk, WorkspaceMembership.Role.VIEWER)
    return render(
        request,
        "versions/list.html",
        {"link": link, "versions": link.versions.select_related("changed_by")},
    )


@login_required
@require_POST
def link_version_rollback(request, link_pk, version_number):
    link = _managed_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    version = get_object_or_404(LinkVersion, link=link, version_number=version_number)
    rollback_link(link, version, request.user)
    record_audit(
        action="LINK_ROLLED_BACK",
        actor=request.user,
        workspace=link.workspace,
        target=link,
        metadata={"restored_version": version_number},
    )
    messages.success(request, f"/{link.shorturl} was restored from version {version_number}.")
    return redirect("link_version_list", link_pk=link.pk)


@login_required
def utm_builder(request):
    form = UtmBuilderForm(request.POST or None)
    generated_url = None
    if request.method == "POST" and form.is_valid():
        generated_url = form.build_url()
    return render(
        request,
        "tools/utm_builder.html",
        {"form": form, "generated_url": generated_url},
    )
