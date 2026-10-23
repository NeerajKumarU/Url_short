from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404

from .models import WorkspaceMembership


ROLE_RANK = {
    WorkspaceMembership.Role.VIEWER: 10,
    WorkspaceMembership.Role.EDITOR: 20,
    WorkspaceMembership.Role.ADMIN: 30,
    WorkspaceMembership.Role.OWNER: 40,
}


def workspace_role(user, workspace):
    if not user.is_authenticated or workspace is None or not workspace.is_active:
        return None
    if user.is_superuser:
        return WorkspaceMembership.Role.OWNER
    membership = WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=user,
        is_active=True,
    ).only("role").first()
    return membership.role if membership else None


def has_workspace_role(user, workspace, minimum_role=WorkspaceMembership.Role.VIEWER):
    role = workspace_role(user, workspace)
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[minimum_role]


def require_workspace_role(user, workspace, minimum_role=WorkspaceMembership.Role.VIEWER):
    if not has_workspace_role(user, workspace, minimum_role):
        raise PermissionDenied("You do not have permission for this workspace action.")


def can_access_link(user, link, minimum_role=WorkspaceMembership.Role.VIEWER):
    if link.workspace_id:
        return has_workspace_role(user, link.workspace, minimum_role)
    return user.is_authenticated and (user.is_superuser or link.owner_id == user.pk)


def require_link_access(user, link, minimum_role=WorkspaceMembership.Role.VIEWER):
    # Use a 404 for tenant-owned objects to avoid confirming their existence.
    if not can_access_link(user, link, minimum_role):
        raise Http404("Link not found")


def platform_admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Platform administrator access is required.")
        return view_func(request, *args, **kwargs)

    return wrapped
