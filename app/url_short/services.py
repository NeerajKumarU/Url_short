from django.db import IntegrityError, transaction
from django.utils.text import slugify

from .models import AuditLog, Workspace, WorkspaceMembership, urlModel


SENSITIVE_METADATA_KEYS = {
    "password",
    "password1",
    "password2",
    "secret",
    "token",
    "api_key",
    "authorization",
}


def _available_workspace_slug(user):
    base = slugify(user.username) or f"user-{user.pk}"
    base = f"{base}-workspace"[:130].strip("-")
    candidate = base
    suffix = 2
    while Workspace.objects.filter(slug=candidate).exists():
        candidate = f"{base[:130 - len(str(suffix))]}-{suffix}"
        suffix += 1
    return candidate


@transaction.atomic
def ensure_personal_workspace(user):
    """Return a user's personal workspace and safely adopt legacy owner-only links."""
    workspace = Workspace.objects.filter(owner=user).order_by("created_at", "pk").first()
    if workspace is None:
        try:
            workspace = Workspace.objects.create(
                name=f"{user.username}'s workspace",
                slug=_available_workspace_slug(user),
                owner=user,
            )
        except IntegrityError:
            workspace = Workspace.objects.filter(owner=user).order_by("created_at", "pk").first()
            if workspace is None:
                raise

    WorkspaceMembership.objects.update_or_create(
        workspace=workspace,
        user=user,
        defaults={"role": WorkspaceMembership.Role.OWNER, "is_active": True},
    )
    urlModel.objects.filter(owner=user, workspace__isnull=True).update(workspace=workspace)
    return workspace


def record_audit(*, action, actor=None, workspace=None, target=None, metadata=None):
    """Write a minimal, secret-filtered audit event."""
    safe_metadata = {}
    for key, value in (metadata or {}).items():
        if key.lower() in SENSITIVE_METADATA_KEYS:
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            safe_metadata[key] = value

    return AuditLog.objects.create(
        workspace=workspace,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_type=target._meta.label if target is not None else "",
        target_id=str(target.pk) if target is not None and target.pk is not None else "",
        metadata=safe_metadata,
    )
