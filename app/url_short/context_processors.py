from .models import AnalyticsAnomaly, ApprovalRequest, WorkspaceMembership


ROLE_RANK = {
    WorkspaceMembership.Role.VIEWER: 10,
    WorkspaceMembership.Role.EDITOR: 20,
    WorkspaceMembership.Role.ADMIN: 30,
    WorkspaceMembership.Role.OWNER: 40,
}


def application_shell(request):
    """Provide lightweight, permission-aware context for the shared SaaS shell."""
    if not request.user.is_authenticated:
        return {}

    memberships = WorkspaceMembership.objects.select_related("workspace").filter(
        user=request.user,
        is_active=True,
        workspace__is_active=True,
    )
    selected_id = request.session.get("workspace_id")
    membership = memberships.filter(workspace_id=selected_id).first() if selected_id else None
    if membership is None:
        membership = memberships.order_by("workspace__created_at", "workspace_id").first()

    workspace = membership.workspace if membership else None
    role = membership.role if membership else None
    role_rank = ROLE_RANK.get(role, 0)
    is_platform_admin = request.user.is_staff or request.user.is_superuser

    anomaly_count = 0
    approval_count = 0
    if workspace is not None:
        anomaly_count = AnalyticsAnomaly.objects.filter(
            workspace=workspace,
            resolved_at__isnull=True,
        ).count()
        if role_rank >= ROLE_RANK[WorkspaceMembership.Role.ADMIN] or request.user.is_superuser:
            approval_count = ApprovalRequest.objects.filter(
                workspace=workspace,
                status=ApprovalRequest.Status.PENDING,
            ).count()

    return {
        "shell_workspace": workspace,
        "shell_membership": membership,
        "shell_role": role,
        "shell_can_edit": role_rank >= ROLE_RANK[WorkspaceMembership.Role.EDITOR] or request.user.is_superuser,
        "shell_can_admin": role_rank >= ROLE_RANK[WorkspaceMembership.Role.ADMIN] or request.user.is_superuser,
        "shell_is_platform_admin": is_platform_admin,
        "shell_anomaly_count": anomaly_count,
        "shell_approval_count": approval_count,
        "shell_notification_count": anomaly_count + approval_count,
    }
