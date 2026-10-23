from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .services import ensure_personal_workspace, record_audit


@receiver(user_logged_in)
def audit_successful_login(sender, request, user, **kwargs):
    workspace = ensure_personal_workspace(user)
    record_audit(action="USER_LOGIN", actor=user, workspace=workspace, target=user)
