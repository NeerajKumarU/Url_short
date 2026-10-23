import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from .models import ApiCredential


KEY_MARKER = "ol_live"


@transaction.atomic
def create_api_credential(*, workspace, name, scopes, created_by, expires_at=None):
    while True:
        prefix = secrets.token_hex(5)
        if not ApiCredential.objects.filter(prefix=prefix).exists():
            break
    raw_key = f"{KEY_MARKER}_{prefix}_{secrets.token_urlsafe(32)}"
    credential = ApiCredential.objects.create(
        workspace=workspace,
        name=name,
        prefix=prefix,
        key_hash=make_password(raw_key),
        scopes=sorted(set(scopes)),
        created_by=created_by,
        expires_at=expires_at,
    )
    return credential, raw_key


def authenticate_api_key(raw_key, required_scope=None):
    if not raw_key or not raw_key.startswith(f"{KEY_MARKER}_"):
        return None, "Invalid API credential."
    parts = raw_key.split("_", 3)
    if len(parts) != 4:
        return None, "Invalid API credential."
    prefix = parts[2]
    credential = ApiCredential.objects.select_related("workspace", "created_by").filter(
        prefix=prefix
    ).first()
    if credential is None or not check_password(raw_key, credential.key_hash):
        return None, "Invalid API credential."
    if not credential.is_active or not credential.workspace.is_active:
        return None, "API credential is expired or revoked."
    if required_scope and required_scope not in credential.scopes:
        return None, f"Missing required scope: {required_scope}."
    ApiCredential.objects.filter(pk=credential.pk).update(last_used_at=timezone.now())
    return credential, None


def bearer_token(request):
    value = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""
