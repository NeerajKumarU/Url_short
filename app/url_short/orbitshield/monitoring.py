from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncMinute
from django.utils import timezone

from ..models import ClickEvent, SecurityIncident, WorkspaceSecuritySettings
from ..services import record_audit


BOT_TYPES = (
    ClickEvent.BotClassification.KNOWN_BOT,
    ClickEvent.BotClassification.LIKELY_BOT,
)
ACTIVE_INCIDENT_STATUSES = (
    SecurityIncident.Status.OPEN,
    SecurityIncident.Status.INVESTIGATING,
)
MINIMUM_SCORE = {
    WorkspaceSecuritySettings.Sensitivity.RELAXED: 40,
    WorkspaceSecuritySettings.Sensitivity.BALANCED: 30,
    WorkspaceSecuritySettings.Sensitivity.HIGH: 20,
}


@dataclass(frozen=True)
class SecurityScanResult:
    incident: SecurityIncident
    created: bool
    escalated: bool


def severity_for_score(score):
    if score >= 80:
        return SecurityIncident.Severity.CRITICAL
    if score >= 60:
        return SecurityIncident.Severity.HIGH
    if score >= 30:
        return SecurityIncident.Severity.MEDIUM
    return SecurityIncident.Severity.LOW


def _signal(name, label, score, maximum, observed, baseline, detail):
    return {
        "name": name,
        "label": label,
        "score": int(score),
        "maximum": maximum,
        "observed": observed,
        "baseline": baseline,
        "detail": detail,
    }


def _analyze_link(link, now):
    current_start = now - timedelta(minutes=15)
    baseline_start = current_start - timedelta(hours=2)
    current = link.clicks.filter(clicked_at__gte=current_start, clicked_at__lt=now)
    observed = current.count()
    if observed < 5:
        return None

    historical = link.clicks.filter(clicked_at__gte=baseline_start, clicked_at__lt=current_start)
    historical_count = historical.count()
    baseline = historical_count / 8
    signals = []

    ratio = observed / max(baseline, 1)
    if observed >= 10 and ratio >= 3:
        score = min(25, 10 + round((ratio - 3) * 3))
        signals.append(_signal(
            "traffic_spike",
            "Traffic spike",
            score,
            25,
            observed,
            round(baseline, 2),
            f"{observed} clicks in 15 minutes versus a {baseline:.1f}-click baseline.",
        ))

    fingerprints = list(
        current.exclude(ip_fingerprint="")
        .values("ip_fingerprint")
        .annotate(value=Count("id"))
        .order_by("-value")[:5]
    )
    top_fingerprint_clicks = fingerprints[0]["value"] if fingerprints else 0
    fingerprint_share = top_fingerprint_clicks / observed if observed else 0
    if top_fingerprint_clicks >= 8 and fingerprint_share >= 0.35:
        score = min(20, round(8 + fingerprint_share * 16))
        signals.append(_signal(
            "repeated_ip",
            "Repeated visitor activity",
            score,
            20,
            round(fingerprint_share * 100, 1),
            35,
            f"One privacy-safe visitor fingerprint generated {top_fingerprint_clicks} clicks ({fingerprint_share:.0%}).",
        ))

    velocity = (
        current.exclude(ip_fingerprint="")
        .annotate(minute=TruncMinute("clicked_at"))
        .values("ip_fingerprint", "minute")
        .annotate(value=Count("id"))
        .order_by("-value")
        .first()
    )
    peak_velocity = velocity["value"] if velocity else 0
    if peak_velocity >= 10:
        score = min(10, 5 + (peak_velocity // 5))
        signals.append(_signal(
            "click_velocity",
            "Abnormal click velocity",
            score,
            10,
            peak_velocity,
            10,
            f"A single visitor fingerprint generated {peak_velocity} clicks within one minute.",
        ))

    bot_count = current.filter(bot_classification__in=BOT_TYPES).count()
    bot_ratio = bot_count / observed if observed else 0
    if observed >= 10 and bot_ratio >= 0.5:
        score = min(20, round(5 + bot_ratio * 18))
        signals.append(_signal(
            "bot_activity",
            "Automated bot activity",
            score,
            20,
            round(bot_ratio * 100, 1),
            50,
            f"{bot_count} of {observed} clicks ({bot_ratio:.0%}) were classified as automated traffic.",
        ))

    geo_current = current.exclude(country_code="")
    geo_count = geo_current.count()
    historical_countries = set(
        link.clicks.filter(
            clicked_at__gte=now - timedelta(days=30),
            clicked_at__lt=current_start,
        ).exclude(country_code="").values_list("country_code", flat=True)
    )
    new_country_count = geo_current.exclude(country_code__in=historical_countries).count() if historical_countries else 0
    new_country_ratio = new_country_count / geo_count if geo_count else 0
    if geo_count >= 10 and historical_countries and new_country_ratio >= 0.5:
        score = min(15, round(5 + new_country_ratio * 12))
        signals.append(_signal(
            "geo_anomaly",
            "Geographic anomaly",
            score,
            15,
            round(new_country_ratio * 100, 1),
            50,
            f"{new_country_count} of {geo_count} geolocated clicks originated from countries not seen in the prior 30 days.",
        ))

    unusual_agents = current.filter(
        Q(user_agent="") | Q(bot_classification=ClickEvent.BotClassification.UNKNOWN)
    ).count()
    agent_ratio = unusual_agents / observed if observed else 0
    if observed >= 10 and agent_ratio >= 0.4:
        score = min(10, round(3 + agent_ratio * 9))
        signals.append(_signal(
            "user_agent_anomaly",
            "User-agent anomaly",
            score,
            10,
            round(agent_ratio * 100, 1),
            40,
            f"{unusual_agents} of {observed} clicks had missing or unrecognized browser signatures.",
        ))

    risk_score = min(100, sum(item["score"] for item in signals))
    if not signals:
        return None
    highest = max(signals, key=lambda item: item["score"])
    threat_map = {
        "traffic_spike": SecurityIncident.ThreatType.TRAFFIC_SPIKE,
        "repeated_ip": SecurityIncident.ThreatType.REPEATED_IP,
        "click_velocity": SecurityIncident.ThreatType.CLICK_VELOCITY,
        "bot_activity": SecurityIncident.ThreatType.BOT_ACTIVITY,
        "geo_anomaly": SecurityIncident.ThreatType.GEO_ANOMALY,
        "user_agent_anomaly": SecurityIncident.ThreatType.USER_AGENT_ANOMALY,
    }
    threat_type = SecurityIncident.ThreatType.COMPOSITE if len(signals) >= 3 else threat_map[highest["name"]]
    explanation = " ".join(item["detail"] for item in sorted(signals, key=lambda item: item["score"], reverse=True))
    return {
        "risk_score": risk_score,
        "severity": severity_for_score(risk_score),
        "threat_type": threat_type,
        "signals": signals,
        "explanation": explanation[:1000],
        "observed_clicks": observed,
        "baseline_clicks": round(baseline, 2),
    }


@transaction.atomic
def _upsert_incident(workspace, link, finding, now):
    incident = (
        SecurityIncident.objects.select_for_update()
        .filter(workspace=workspace, link=link, status__in=ACTIVE_INCIDENT_STATUSES)
        .first()
    )
    created = incident is None
    previous_score = incident.risk_score if incident else 0
    previous_severity = incident.severity if incident else None
    if incident is None:
        incident = SecurityIncident(workspace=workspace, link=link, first_detected_at=now)
    for field, value in finding.items():
        setattr(incident, field, value)
    incident.last_detected_at = now
    incident.save()
    escalated = not created and (
        incident.risk_score > previous_score
        and incident.severity != previous_severity
    )
    if created:
        record_audit(
            action="SECURITY_INCIDENT_CREATED",
            workspace=workspace,
            target=incident,
            metadata={"link_id": link.pk, "risk_score": incident.risk_score, "severity": incident.severity},
        )
    elif escalated:
        record_audit(
            action="SECURITY_INCIDENT_ESCALATED",
            workspace=workspace,
            target=incident,
            metadata={"link_id": link.pk, "risk_score": incident.risk_score, "severity": incident.severity},
        )
    return SecurityScanResult(incident=incident, created=created, escalated=escalated)


def scan_workspace_security(workspace, now=None):
    now = now or timezone.now()
    settings, _ = WorkspaceSecuritySettings.objects.get_or_create(workspace=workspace)
    if not settings.monitoring_enabled:
        return []
    minimum = MINIMUM_SCORE[settings.sensitivity]
    results = []
    links = workspace.links.filter(is_enabled=True, security_disabled=False).exclude(
        suspended_until__gt=now,
    )
    for link in links.iterator():
        finding = _analyze_link(link, now)
        if finding and finding["risk_score"] >= minimum:
            result = _upsert_incident(workspace, link, finding, now)
            results.append(result)
            if settings.automatic_throttling and result.incident.risk_score >= 90:
                link.suspended_until = now + timedelta(minutes=15)
                link.suspension_reason = "OrbitShield automatic critical-risk throttle"
                link.save(update_fields=("suspended_until", "suspension_reason", "updated_at"))
                record_audit(
                    action="LINK_AUTOMATICALLY_THROTTLED",
                    workspace=workspace,
                    target=link,
                    metadata={"incident_id": result.incident.pk, "risk_score": result.incident.risk_score},
                )
    return results
