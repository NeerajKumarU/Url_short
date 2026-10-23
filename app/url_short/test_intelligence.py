from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .anomalies import detect_workspace_anomalies
from .models import AnalyticsAnomaly, ClickEvent, NotificationDelivery, urlModel
from .notifications import send_notification
from .retention import anonymize_expired_visitor_data
from .services import ensure_personal_workspace


User = get_user_model()


class RealtimeAndGeoAnalyticsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("analytics-owner", password="safe-password-123")
        self.other = User.objects.create_user("analytics-other", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.other_workspace = ensure_personal_workspace(self.other)
        self.link = urlModel.objects.create(workspace=self.workspace, owner=self.owner, shorturl="geo-link", longurl="https://example.com")
        self.other_link = urlModel.objects.create(workspace=self.other_workspace, owner=self.other, shorturl="other-geo-link", longurl="https://example.org")

    @override_settings(ORBITLINK_TRUST_CLOUDFLARE_GEO=True)
    def test_trusted_cloudflare_geo_is_derived_on_click(self):
        self.client.get(
            "/geo-link",
            HTTP_CF_IPCOUNTRY="IN",
            HTTP_CF_REGION="Karnataka",
            HTTP_CF_IPCITY="Bengaluru",
        )
        event = ClickEvent.objects.get(short_url=self.link)
        self.assertEqual(event.country_code, "IN")
        self.assertEqual(event.region, "Karnataka")
        self.assertEqual(event.city, "Bengaluru")

    def test_realtime_endpoint_is_workspace_isolated(self):
        ClickEvent.objects.create(short_url=self.link, bot_classification=ClickEvent.BotClassification.HUMAN)
        ClickEvent.objects.create(short_url=self.other_link, bot_classification=ClickEvent.BotClassification.HUMAN)
        self.client.force_login(self.owner)
        response = self.client.get("/analytics/realtime/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["clicks_last_5_minutes"], 1)
        self.assertEqual(payload["clicks_today"], 1)
        self.assertEqual(payload["top_links_24h"][0]["shorturl"], "geo-link")


class ExplainableAnomalyTests(TestCase):
    def test_traffic_spike_creates_explained_deduplicated_finding(self):
        owner = User.objects.create_user("anomaly-owner", password="safe-password-123")
        workspace = ensure_personal_workspace(owner)
        link = urlModel.objects.create(workspace=workspace, owner=owner, shorturl="spike", longurl="https://example.com")
        for _ in range(10):
            ClickEvent.objects.create(short_url=link, bot_classification=ClickEvent.BotClassification.HUMAN)
        findings = detect_workspace_anomalies(workspace)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].anomaly_type, AnalyticsAnomaly.AnomalyType.TRAFFIC_SPIKE)
        self.assertIn("last 15 minutes", findings[0].explanation)
        self.assertEqual(detect_workspace_anomalies(workspace), [])


class PrivacyRetentionAndNotificationTests(TestCase):
    def test_retention_anonymizes_ip_but_keeps_aggregate_event(self):
        owner = User.objects.create_user("privacy-owner", password="safe-password-123")
        workspace = ensure_personal_workspace(owner)
        workspace.analytics_retention_days = 7
        workspace.save(update_fields=("analytics_retention_days",))
        link = urlModel.objects.create(workspace=workspace, owner=owner, shorturl="privacy", longurl="https://example.com")
        event = ClickEvent.objects.create(short_url=link, ip_address="203.0.113.10")
        ClickEvent.objects.filter(pk=event.pk).update(clicked_at=timezone.now() - timedelta(days=8))
        self.assertEqual(anonymize_expired_visitor_data(), 1)
        event.refresh_from_db()
        self.assertIsNone(event.ip_address)
        self.assertTrue(ClickEvent.objects.filter(pk=event.pk).exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_notification_uses_django_email_backend_and_records_result(self):
        delivery = send_notification(
            event_type="APPROVAL_REQUIRED",
            recipient="owner@example.com",
            subject="Review required",
            body="A link needs review.",
        )
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)
