import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncHour
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import AuditLog, ClickEvent, SecurityIncident, WorkspaceMembership, WorkspaceSecuritySettings
from .permissions import require_workspace_role
from .orbitshield.actions import apply_incident_action
from .orbitshield.monitoring import scan_workspace_security
from .selectors import get_current_workspace, links_for_workspace


SECURITY_AUDIT_ACTIONS = (
    "SECURITY_INCIDENT_CREATED",
    "SECURITY_INCIDENT_ESCALATED",
    "SECURITY_INCIDENT_INVESTIGATED",
    "SECURITY_INCIDENT_RESOLVED",
    "SECURITY_INCIDENT_DISMISSED",
    "LINK_TEMPORARILY_SUSPENDED",
    "LINK_SECURITY_DISABLED",
    "LINK_SECURITY_REACTIVATED",
    "LINK_SECURITY_SUSPENSION_EXPIRED",
    "LINK_AUTOMATICALLY_THROTTLED",
)


def _incident_payload(incident):
    link = incident.link
    return {
        "id": incident.pk,
        "risk_score": incident.risk_score,
        "severity": incident.severity,
        "severity_label": incident.get_severity_display(),
        "status": incident.status,
        "status_label": incident.get_status_display(),
        "threat_type": incident.threat_type,
        "threat_label": incident.get_threat_type_display(),
        "signals": incident.signals,
        "explanation": incident.explanation,
        "observed_clicks": incident.observed_clicks,
        "baseline_clicks": incident.baseline_clicks,
        "first_detected_at": incident.first_detected_at,
        "last_detected_at": incident.last_detected_at,
        "resolution_note": incident.resolution_note,
        "resolved_at": incident.resolved_at,
        "investigated_by": incident.investigated_by.username if incident.investigated_by_id else None,
        "link": {
            "id": link.pk,
            "alias": link.shorturl,
            "status": link.status_label,
            "security_disabled": link.security_disabled,
            "suspended_until": link.suspended_until,
        } if link else None,
    }


def build_security_payload(request, workspace):
    links = links_for_workspace(request.user, workspace)
    incidents = SecurityIncident.objects.filter(workspace=workspace).select_related("link", "investigated_by")
    status = request.GET.get("status", "all").upper()
    severity = request.GET.get("severity", "all").upper()
    threat = request.GET.get("threat", "all").upper()
    query = request.GET.get("q", "").strip()
    if status in SecurityIncident.Status.values:
        incidents = incidents.filter(status=status)
    if severity in SecurityIncident.Severity.values:
        incidents = incidents.filter(severity=severity)
    if threat in SecurityIncident.ThreatType.values:
        incidents = incidents.filter(threat_type=threat)
    if query:
        incidents = incidents.filter(Q(link__shorturl__icontains=query) | Q(explanation__icontains=query))

    now = timezone.now()
    start = now - timedelta(hours=23)
    hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    events = ClickEvent.objects.filter(short_url__in=links, clicked_at__gte=start)
    bot_types = (ClickEvent.BotClassification.KNOWN_BOT, ClickEvent.BotClassification.LIKELY_BOT)
    hourly_events = {
        row["hour"]: row
        for row in events.annotate(hour=TruncHour("clicked_at")).values("hour").annotate(
            total=Count("id"),
            automated=Count("id", filter=Q(bot_classification__in=bot_types)),
        )
    }
    hourly_risk = {
        row["hour"]: row["risk"] or 0
        for row in SecurityIncident.objects.filter(workspace=workspace, last_detected_at__gte=start)
        .annotate(hour=TruncHour("last_detected_at"))
        .values("hour")
        .annotate(risk=Max("risk_score"))
    }
    timeline = []
    for offset in range(24):
        hour = hour_start + timedelta(hours=offset)
        values = hourly_events.get(hour, {})
        timeline.append({
            "time": hour,
            "label": hour.strftime("%H:%M"),
            "total": values.get("total", 0),
            "automated": values.get("automated", 0),
            "risk": hourly_risk.get(hour, 0),
        })

    active_statuses = (SecurityIncident.Status.OPEN, SecurityIncident.Status.INVESTIGATING)
    active = SecurityIncident.objects.filter(workspace=workspace, status__in=active_statuses)
    total_events = events.count()
    automated_events = events.filter(bot_classification__in=bot_types).count()
    settings, _ = WorkspaceSecuritySettings.objects.get_or_create(workspace=workspace)

    targeted_rows = list(
        SecurityIncident.objects.filter(workspace=workspace, link__isnull=False)
        .values("link_id", "link__shorturl")
        .annotate(incident_count=Count("id"), max_risk=Max("risk_score"), latest=Max("last_detected_at"))
        .order_by("-max_risk", "-latest")[:6]
    )
    link_map = {link.pk: link for link in links.filter(pk__in=[row["link_id"] for row in targeted_rows])}
    targeted = [
        {
            "id": row["link_id"],
            "alias": row["link__shorturl"],
            "incidents": row["incident_count"],
            "risk_score": row["max_risk"],
            "status": link_map[row["link_id"]].status_label if row["link_id"] in link_map else "Unavailable",
        }
        for row in targeted_rows
    ]
    bot_breakdown = [
        {"label": label, "value": events.filter(bot_classification=value).count(), "key": value}
        for value, label in ClickEvent.BotClassification.choices
    ]
    countries = list(
        events.exclude(country_code="").values("country_code").annotate(value=Count("id")).order_by("-value")[:8]
    )
    activity = [
        {
            "id": item.pk,
            "action": item.action,
            "actor": item.actor.username if item.actor_id else "OrbitShield",
            "created_at": item.created_at,
            "target_id": item.target_id,
            "metadata": item.metadata,
        }
        for item in AuditLog.objects.filter(workspace=workspace, action__in=SECURITY_AUDIT_ACTIONS).select_related("actor")[:20]
    ]
    return {
        "workspace_name": workspace.name,
        "summary": {
            "risk_score": active.aggregate(value=Max("risk_score"))["value"] or 0,
            "open_incidents": active.count(),
            "critical_incidents": active.filter(severity=SecurityIncident.Severity.CRITICAL).count(),
            "suspicious_clicks": automated_events,
            "bot_percentage": round((automated_events / total_events) * 100, 1) if total_events else 0,
            "monitored_links": links.filter(is_enabled=True).count(),
        },
        "incidents": [_incident_payload(item) for item in incidents[:100]],
        "timeline": timeline,
        "targeted_links": targeted,
        "bot_breakdown": bot_breakdown,
        "countries": [{"country": row["country_code"], "value": row["value"]} for row in countries],
        "activity": activity,
        "settings": {
            "monitoring_enabled": settings.monitoring_enabled,
            "sensitivity": settings.sensitivity,
            "alert_threshold": settings.alert_threshold,
            "email_alerts": settings.email_alerts,
            "webhook_alerts": settings.webhook_alerts,
            "automatic_throttling": settings.automatic_throttling,
        },
        "can_admin": request.user.is_superuser or request.user.workspace_memberships.filter(
            workspace=workspace,
            is_active=True,
            role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.ADMIN),
        ).exists(),
    }


@login_required
@require_GET
def security_overview(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    return JsonResponse({"page": build_security_payload(request, workspace)})


@login_required
@require_GET
def security_incident_detail(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    incident = get_object_or_404(
        SecurityIncident.objects.select_related("link", "investigated_by"),
        pk=pk,
        workspace=workspace,
    )
    return JsonResponse({"incident": _incident_payload(incident)})


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        raise ValidationError("Enter a valid JSON request body.")


def _boolean_setting(body, key, current):
    value = body.get(key, current)
    if not isinstance(value, bool):
        raise ValidationError(f"{key.replace('_', ' ').capitalize()} must be true or false.")
    return value


@login_required
@require_POST
def security_incident_action(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    incident = get_object_or_404(SecurityIncident, pk=pk, workspace=workspace)
    try:
        body = _json_body(request)
        incident = apply_incident_action(
            incident=incident,
            actor=request.user,
            action=body.get("action", ""),
            note=body.get("note", ""),
        )
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)
    incident.refresh_from_db()
    return JsonResponse({"incident": _incident_payload(incident)})


@login_required
@require_POST
def security_settings_update(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    try:
        body = _json_body(request)
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)
    settings, _ = WorkspaceSecuritySettings.objects.get_or_create(workspace=workspace)
    sensitivity = body.get("sensitivity", settings.sensitivity)
    if sensitivity not in WorkspaceSecuritySettings.Sensitivity.values:
        return JsonResponse({"error": "Select a valid monitoring sensitivity."}, status=400)
    try:
        threshold = int(body.get("alert_threshold", settings.alert_threshold))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Alert threshold must be a number."}, status=400)
    if not 20 <= threshold <= 100:
        return JsonResponse({"error": "Alert threshold must be between 20 and 100."}, status=400)
    try:
        settings.monitoring_enabled = _boolean_setting(body, "monitoring_enabled", settings.monitoring_enabled)
        settings.email_alerts = _boolean_setting(body, "email_alerts", settings.email_alerts)
        settings.webhook_alerts = _boolean_setting(body, "webhook_alerts", settings.webhook_alerts)
        settings.automatic_throttling = _boolean_setting(body, "automatic_throttling", settings.automatic_throttling)
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)
    settings.sensitivity = sensitivity
    settings.alert_threshold = threshold
    settings.save()
    return JsonResponse({"settings": build_security_payload(request, workspace)["settings"]})


@login_required
@require_POST
def security_scan_now(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    results = scan_workspace_security(workspace)
    return JsonResponse({
        "created": sum(1 for item in results if item.created),
        "updated": sum(1 for item in results if not item.created),
    })
