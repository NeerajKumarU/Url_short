from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import AnalyticsAnomaly, ClickEvent


DEDUPE_WINDOW = timedelta(minutes=15)


def _create_once(*, workspace, link, anomaly_type, severity, baseline, observed, explanation):
    if AnalyticsAnomaly.objects.filter(
        workspace=workspace,
        link=link,
        anomaly_type=anomaly_type,
        detected_at__gte=timezone.now() - DEDUPE_WINDOW,
    ).exists():
        return None
    return AnalyticsAnomaly.objects.create(
        workspace=workspace,
        link=link,
        anomaly_type=anomaly_type,
        severity=severity,
        baseline_value=round(baseline, 2),
        observed_value=round(observed, 2),
        explanation=explanation[:500],
    )


def detect_workspace_anomalies(workspace, now=None):
    now = now or timezone.now()
    current_start = now - timedelta(minutes=15)
    baseline_start = now - timedelta(hours=2, minutes=15)
    created = []
    links = workspace.links.filter(is_enabled=True)
    for link in links:
        current = link.clicks.filter(clicked_at__gte=current_start, clicked_at__lt=now)
        historical_count = link.clicks.filter(
            clicked_at__gte=baseline_start,
            clicked_at__lt=current_start,
        ).count()
        observed = current.count()
        baseline = historical_count / 8
        if observed >= max(10, baseline * 3):
            anomaly = _create_once(
                workspace=workspace,
                link=link,
                anomaly_type=AnalyticsAnomaly.AnomalyType.TRAFFIC_SPIKE,
                severity=AnalyticsAnomaly.Severity.CRITICAL if observed >= max(50, baseline * 6) else AnalyticsAnomaly.Severity.WARNING,
                baseline=baseline,
                observed=observed,
                explanation=f"The last 15 minutes recorded {observed} clicks versus a {baseline:.1f}-click 15-minute baseline from the preceding two hours.",
            )
            if anomaly:
                created.append(anomaly)
        elif baseline >= 10 and observed <= baseline * 0.25:
            anomaly = _create_once(
                workspace=workspace,
                link=link,
                anomaly_type=AnalyticsAnomaly.AnomalyType.TRAFFIC_DROP,
                severity=AnalyticsAnomaly.Severity.WARNING,
                baseline=baseline,
                observed=observed,
                explanation=f"The last 15 minutes recorded {observed} clicks, at most 25% of the {baseline:.1f}-click baseline.",
            )
            if anomaly:
                created.append(anomaly)

        bot_count = current.filter(
            bot_classification__in=(
                ClickEvent.BotClassification.KNOWN_BOT,
                ClickEvent.BotClassification.LIKELY_BOT,
            )
        ).count()
        bot_ratio = bot_count / observed if observed else 0
        if observed >= 10 and bot_ratio >= 0.8:
            anomaly = _create_once(
                workspace=workspace,
                link=link,
                anomaly_type=AnalyticsAnomaly.AnomalyType.BOT_SPIKE,
                severity=AnalyticsAnomaly.Severity.WARNING,
                baseline=0.8,
                observed=bot_ratio,
                explanation=f"{bot_count} of {observed} clicks ({bot_ratio:.0%}) in the last 15 minutes were classified as bots.",
            )
            if anomaly:
                created.append(anomaly)
    return created
