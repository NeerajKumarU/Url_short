from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import SecurityIncident, urlModel
from ..services import record_audit


VALID_ACTIONS = {
    "investigate",
    "resolve",
    "dismiss",
    "suspend_1h",
    "suspend_24h",
    "disable",
    "resume",
}


@transaction.atomic
def apply_incident_action(*, incident, actor, action, note=""):
    if action not in VALID_ACTIONS:
        raise ValidationError("Unsupported security action.")
    incident = SecurityIncident.objects.select_for_update().select_related("link", "workspace").get(pk=incident.pk)
    link = urlModel.objects.select_for_update().filter(pk=incident.link_id).first() if incident.link_id else None
    now = timezone.now()
    note = (note or "").strip()[:2000]

    if action == "investigate":
        incident.status = SecurityIncident.Status.INVESTIGATING
    elif action == "resolve":
        incident.status = SecurityIncident.Status.RESOLVED
        incident.resolved_at = now
    elif action == "dismiss":
        incident.status = SecurityIncident.Status.DISMISSED
        incident.resolved_at = now
    elif link is None:
        raise ValidationError("The affected link is no longer available.")
    elif action in {"suspend_1h", "suspend_24h"}:
        hours = 1 if action == "suspend_1h" else 24
        link.suspended_until = now + timedelta(hours=hours)
        link.suspension_reason = f"OrbitShield incident #{incident.pk}: {note or incident.explanation}"[:500]
        link.save(update_fields=("suspended_until", "suspension_reason", "updated_at"))
        incident.status = SecurityIncident.Status.INVESTIGATING
    elif action == "disable":
        link.security_disabled = True
        link.suspended_until = None
        link.suspension_reason = f"OrbitShield incident #{incident.pk}: {note or incident.explanation}"[:500]
        link.save(update_fields=("security_disabled", "suspended_until", "suspension_reason", "updated_at"))
        incident.status = SecurityIncident.Status.INVESTIGATING
    elif action == "resume":
        link.security_disabled = False
        link.suspended_until = None
        link.suspension_reason = ""
        link.save(update_fields=("security_disabled", "suspended_until", "suspension_reason", "updated_at"))
        incident.status = SecurityIncident.Status.INVESTIGATING

    incident.investigated_by = actor
    if note:
        incident.resolution_note = note
    incident.save(update_fields=("status", "investigated_by", "resolution_note", "resolved_at", "updated_at"))
    record_audit(
        action={
            "investigate": "SECURITY_INCIDENT_INVESTIGATED",
            "resolve": "SECURITY_INCIDENT_RESOLVED",
            "dismiss": "SECURITY_INCIDENT_DISMISSED",
            "suspend_1h": "LINK_TEMPORARILY_SUSPENDED",
            "suspend_24h": "LINK_TEMPORARILY_SUSPENDED",
            "disable": "LINK_SECURITY_DISABLED",
            "resume": "LINK_SECURITY_REACTIVATED",
        }[action],
        actor=actor,
        workspace=incident.workspace,
        target=link or incident,
        metadata={"incident_id": incident.pk, "action": action, "risk_score": incident.risk_score},
    )
    return incident


def expire_link_suspensions(workspace, now=None):
    now = now or timezone.now()
    expired = list(
        workspace.links.filter(
            suspended_until__isnull=False,
            suspended_until__lte=now,
            security_disabled=False,
        )
    )
    for link in expired:
        link.suspended_until = None
        link.suspension_reason = ""
        link.save(update_fields=("suspended_until", "suspension_reason", "updated_at"))
        record_audit(
            action="LINK_SECURITY_SUSPENSION_EXPIRED",
            workspace=workspace,
            target=link,
            metadata={"alias": link.shorturl},
        )
    return len(expired)
