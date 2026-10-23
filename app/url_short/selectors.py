from django.db.models import Q

from .models import Campaign, WorkspaceMembership, urlModel
from .services import ensure_personal_workspace


def get_current_workspace(request):
    memberships = WorkspaceMembership.objects.select_related("workspace").filter(
        user=request.user,
        is_active=True,
        workspace__is_active=True,
    )
    selected_id = request.session.get("workspace_id")
    membership = memberships.filter(workspace_id=selected_id).first() if selected_id else None
    if membership is None:
        membership = memberships.order_by("workspace__created_at", "workspace_id").first()
    workspace = membership.workspace if membership else ensure_personal_workspace(request.user)
    request.session["workspace_id"] = workspace.pk
    return workspace


def links_for_workspace(user, workspace):
    return urlModel.objects.filter(
        Q(workspace=workspace) | Q(workspace__isnull=True, owner=user)
    ).distinct()


def campaigns_for_workspace(workspace):
    return Campaign.objects.filter(workspace=workspace)
