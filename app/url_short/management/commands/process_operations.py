from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from url_short.anomalies import detect_workspace_anomalies
from url_short.models import AnalyticsAnomaly, AuditLog, NotificationDelivery, WebhookDelivery, Workspace, WorkspaceSecuritySettings, urlModel
from url_short.notifications import send_notification
from url_short.retention import anonymize_expired_visitor_data
from url_short.webhooks import deliver_webhook
from url_short.webhooks import queue_webhook_event
from url_short.orbitshield.actions import expire_link_suspensions
from url_short.orbitshield.monitoring import scan_workspace_security


class Command(BaseCommand):
    help = "Run OrbitLink retry, anomaly, retention, and lifecycle notification jobs."

    def handle(self, *args, **options):
        now = timezone.now()
        retries = WebhookDelivery.objects.select_related("endpoint").filter(
            endpoint__is_active=True,
        ).filter(
            Q(status=WebhookDelivery.Status.PENDING)
            | Q(status=WebhookDelivery.Status.RETRYING, next_retry_at__lte=now)
        )[:100]
        retry_count = 0
        for delivery in retries:
            deliver_webhook(delivery)
            retry_count += 1

        anomaly_count = 0
        security_incident_count = 0
        expired_suspension_count = 0
        notification_count = 0
        for workspace in Workspace.objects.filter(is_active=True).select_related("owner"):
            security_settings, _ = WorkspaceSecuritySettings.objects.get_or_create(workspace=workspace)
            expired_suspension_count += expire_link_suspensions(workspace, now=now)
            security_results = scan_workspace_security(workspace, now=now)
            security_incident_count += sum(1 for result in security_results if result.created)
            for result in security_results:
                incident = result.incident
                should_alert = (result.created or result.escalated) and incident.risk_score >= security_settings.alert_threshold
                if not should_alert:
                    continue
                payload = {
                    "incident_id": incident.pk,
                    "link_id": incident.link_id,
                    "risk_score": incident.risk_score,
                    "severity": incident.severity,
                    "threat_type": incident.threat_type,
                }
                if security_settings.webhook_alerts:
                    queue_webhook_event(workspace, "SECURITY_INCIDENT", payload)
                if security_settings.email_alerts and workspace.owner.email:
                    alias = incident.link.shorturl if incident.link_id else "deleted link"
                    send_notification(
                        event_type="SECURITY_INCIDENT",
                        recipient=workspace.owner.email,
                        subject=f"OrbitShield {incident.get_severity_display().lower()} risk on /{alias}",
                        body=f"Risk score {incident.risk_score}/100. {incident.explanation}\n\nReview the incident in the OrbitShield Security Center.",
                        workspace=workspace,
                    )
                    notification_count += 1
            anomalies = detect_workspace_anomalies(workspace, now=now)
            anomaly_count += len(anomalies)
            for anomaly in anomalies:
                if anomaly.anomaly_type == AnalyticsAnomaly.AnomalyType.TRAFFIC_SPIKE:
                    queue_webhook_event(
                        workspace,
                        "TRAFFIC_SPIKE",
                        {"anomaly_id": anomaly.pk, "link_id": anomaly.link_id, "observed": anomaly.observed_value},
                    )
            if anomalies and workspace.owner.email:
                subject = f"OrbitLink detected {len(anomalies)} traffic anomaly finding(s)"
                send_notification(
                    event_type="TRAFFIC_ANOMALY",
                    recipient=workspace.owner.email,
                    subject=subject,
                    body="Review the explainable anomaly findings in your OrbitLink workspace.",
                    workspace=workspace,
                )
                notification_count += 1

            ending = workspace.links.filter(
                expires_at__gt=now,
                expires_at__lte=now + timedelta(hours=24),
                is_enabled=True,
            )
            for link in ending:
                subject = f"OrbitLink link /{link.shorturl} expires soon"
                if workspace.owner.email and not NotificationDelivery.objects.filter(
                    workspace=workspace,
                    event_type="LINK_EXPIRING_SOON",
                    subject=subject,
                ).exists():
                    send_notification(
                        event_type="LINK_EXPIRING_SOON",
                        recipient=workspace.owner.email,
                        subject=subject,
                        body=f"/{link.shorturl} expires at {link.expires_at.isoformat()}.",
                        workspace=workspace,
                    )
                    notification_count += 1

            expired = workspace.links.filter(expires_at__lte=now)
            for link in expired:
                if not AuditLog.objects.filter(action="LINK_EXPIRED", target_type="urlModel", target_id=str(link.pk)).exists():
                    AuditLog.objects.create(
                        workspace=workspace,
                        action="LINK_EXPIRED",
                        target_type="urlModel",
                        target_id=str(link.pk),
                        metadata={"alias": link.shorturl},
                    )
                    queue_webhook_event(workspace, "LINK_EXPIRED", {"link_id": link.pk, "alias": link.shorturl})
                    if workspace.owner.email:
                        send_notification(
                            event_type="LINK_EXPIRED",
                            recipient=workspace.owner.email,
                            subject=f"OrbitLink link /{link.shorturl} expired",
                            body=f"/{link.shorturl} expired at {link.expires_at.isoformat()}.",
                            workspace=workspace,
                        )
                        notification_count += 1

            blocked = workspace.links.filter(safety_status=urlModel.SafetyStatus.MALICIOUS)
            for link in blocked:
                if not AuditLog.objects.filter(action="LINK_BLOCKED", target_type="urlModel", target_id=str(link.pk)).exists():
                    AuditLog.objects.create(
                        workspace=workspace,
                        action="LINK_BLOCKED",
                        target_type="urlModel",
                        target_id=str(link.pk),
                        metadata={"alias": link.shorturl, "reason": link.safety_detail},
                    )
                    queue_webhook_event(workspace, "LINK_BLOCKED", {"link_id": link.pk, "alias": link.shorturl})
                    if workspace.owner.email:
                        send_notification(
                            event_type="MALICIOUS_URL_DETECTED",
                            recipient=workspace.owner.email,
                            subject=f"OrbitLink blocked /{link.shorturl}",
                            body=f"/{link.shorturl} is blocked because its destination was marked malicious.",
                            workspace=workspace,
                        )
                        notification_count += 1

            campaigns = workspace.campaigns.filter(
                end_at__gt=now,
                end_at__lte=now + timedelta(hours=24),
                status="ACTIVE",
            )
            for campaign in campaigns:
                subject = f"OrbitLink campaign {campaign.name} ends soon"
                if workspace.owner.email and not NotificationDelivery.objects.filter(
                    workspace=workspace,
                    event_type="CAMPAIGN_ENDING",
                    subject=subject,
                ).exists():
                    send_notification(
                        event_type="CAMPAIGN_ENDING",
                        recipient=workspace.owner.email,
                        subject=subject,
                        body=f"{campaign.name} ends at {campaign.end_at.isoformat()}.",
                        workspace=workspace,
                    )
                    notification_count += 1

        anonymized = anonymize_expired_visitor_data(now=now)
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {retry_count} webhook retries, {anomaly_count} analytics anomalies, "
                f"{security_incident_count} new security incidents, {expired_suspension_count} expired suspensions, "
                f"{notification_count} notifications, and anonymized {anonymized} IP values."
            )
        )
