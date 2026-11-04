import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone

from .models import AuditLog, ClickEvent, NotificationDelivery, SecurityIncident, WorkspaceMembership, WorkspaceSecuritySettings, urlModel
from .orbitshield.actions import expire_link_suspensions
from .orbitshield.fingerprints import fingerprint_ip
from .orbitshield.monitoring import scan_workspace_security
from .security_views import security_incident_detail
from .services import ensure_personal_workspace
from .views import redirecturl


User = get_user_model()


class OrbitShieldMonitoringTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("shield-owner", "shield@example.com", "safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.link = urlModel.objects.create(
            workspace=self.workspace,
            owner=self.owner,
            shorturl="protected-link",
            longurl="https://example.com/protected",
        )

    def suspicious_clicks(self, count=20):
        return ClickEvent.objects.bulk_create([
            ClickEvent(
                short_url=self.link,
                ip_fingerprint="a" * 64,
                user_agent="",
                bot_classification=ClickEvent.BotClassification.LIKELY_BOT,
                bot_reason="Automation marker",
                country_code="US",
            )
            for _ in range(count)
        ])

    @override_settings(ORBITLINK_STORE_VISITOR_IPS=False, ORBITLINK_IP_FINGERPRINT_SECRET="test-fingerprint-secret")
    def test_redirect_records_private_fingerprint_without_storing_raw_ip(self):
        response = self.client.get(
            "/protected-link",
            REMOTE_ADDR="203.0.113.45",
            HTTP_USER_AGENT="Mozilla/5.0 Firefox/120",
        )
        self.assertEqual(response.status_code, 302)
        event = ClickEvent.objects.get(short_url=self.link)
        self.assertIsNone(event.ip_address)
        self.assertEqual(len(event.ip_fingerprint), 64)
        self.assertNotIn("203.0.113.45", event.ip_fingerprint)
        self.assertNotEqual(
            fingerprint_ip("203.0.113.45", "workspace:1"),
            fingerprint_ip("203.0.113.45", "workspace:2"),
        )

    def test_combined_suspicious_signals_create_explainable_critical_incident(self):
        self.suspicious_clicks()
        results = scan_workspace_security(self.workspace)
        self.assertEqual(len(results), 1)
        incident = results[0].incident
        self.assertTrue(results[0].created)
        self.assertGreaterEqual(incident.risk_score, 80)
        self.assertEqual(incident.severity, SecurityIncident.Severity.CRITICAL)
        signal_names = {signal["name"] for signal in incident.signals}
        self.assertIn("traffic_spike", signal_names)
        self.assertIn("repeated_ip", signal_names)
        self.assertIn("bot_activity", signal_names)
        self.assertNotIn("203.0.113", incident.explanation)

    def test_scan_updates_active_incident_instead_of_alert_flooding(self):
        self.suspicious_clicks()
        first = scan_workspace_security(self.workspace)
        second = scan_workspace_security(self.workspace)
        self.assertTrue(first[0].created)
        self.assertFalse(second[0].created)
        self.assertEqual(SecurityIncident.objects.filter(workspace=self.workspace).count(), 1)

    def test_normal_low_volume_clicks_do_not_create_incident(self):
        ClickEvent.objects.create(
            short_url=self.link,
            ip_fingerprint="b" * 64,
            user_agent="Mozilla/5.0 Firefox/120",
            bot_classification=ClickEvent.BotClassification.HUMAN,
        )
        self.assertEqual(scan_workspace_security(self.workspace), [])
        self.assertFalse(SecurityIncident.objects.exists())

    def test_monitoring_can_be_disabled(self):
        settings = WorkspaceSecuritySettings.objects.create(workspace=self.workspace, monitoring_enabled=False)
        self.suspicious_clicks()
        self.assertEqual(scan_workspace_security(self.workspace), [])
        settings.refresh_from_db()
        self.assertFalse(settings.monitoring_enabled)

    def test_critical_composite_risk_can_automatically_throttle_link(self):
        historical = ClickEvent.objects.bulk_create([
            ClickEvent(
                short_url=self.link,
                ip_fingerprint=f"{index:064d}",
                user_agent="Mozilla/5.0 Firefox/120",
                bot_classification=ClickEvent.BotClassification.HUMAN,
                country_code="US",
            )
            for index in range(10)
        ])
        ClickEvent.objects.filter(pk__in=[event.pk for event in historical]).update(
            clicked_at=timezone.now() - timedelta(days=1),
        )
        current = self.suspicious_clicks(25)
        ClickEvent.objects.filter(pk__in=[event.pk for event in current]).update(country_code="IN")
        WorkspaceSecuritySettings.objects.create(workspace=self.workspace, automatic_throttling=True)

        results = scan_workspace_security(self.workspace)
        self.assertGreaterEqual(results[0].incident.risk_score, 90)
        self.link.refresh_from_db()
        self.assertGreater(self.link.suspended_until, timezone.now())
        self.assertTrue(AuditLog.objects.filter(action="LINK_AUTOMATICALLY_THROTTLED").exists())

    def test_scheduled_operation_sends_threshold_security_alert(self):
        self.suspicious_clicks()
        call_command("process_operations", stdout=StringIO())
        delivery = NotificationDelivery.objects.get(event_type="SECURITY_INCIDENT")
        self.assertEqual(delivery.recipient, self.owner.email)
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)


class OrbitShieldSecurityApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("security-admin", "admin@example.com", "safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.link = urlModel.objects.create(
            workspace=self.workspace,
            owner=self.owner,
            shorturl="incident-link",
            longurl="https://example.com/security",
        )
        self.incident = SecurityIncident.objects.create(
            workspace=self.workspace,
            link=self.link,
            threat_type=SecurityIncident.ThreatType.COMPOSITE,
            severity=SecurityIncident.Severity.HIGH,
            status=SecurityIncident.Status.OPEN,
            risk_score=74,
            signals=[{"name": "bot_activity", "label": "Automated bot activity", "score": 20, "maximum": 20, "observed": 90, "baseline": 50, "detail": "Automated traffic."}],
            explanation="Automated traffic was detected.",
            observed_clicks=50,
            baseline_clicks=5,
        )
        self.client.force_login(self.owner)

    def test_security_bootstrap_contains_real_incidents_without_raw_ip(self):
        ClickEvent.objects.create(
            short_url=self.link,
            ip_address="198.51.100.20",
            ip_fingerprint="c" * 64,
            bot_classification=ClickEvent.BotClassification.LIKELY_BOT,
            country_code="IN",
        )
        response = self.client.get("/react/api/bootstrap/", {"_view": "security"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()["page"]
        self.assertEqual(payload["summary"]["open_incidents"], 1)
        self.assertEqual(payload["incidents"][0]["id"], self.incident.pk)
        self.assertNotContains(response, "198.51.100.20")
        self.assertNotContains(response, "cccccccccccccccc")

    def test_admin_can_suspend_and_resume_link(self):
        suspend = self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "suspend_1h", "note": "Investigating automation"}),
            content_type="application/json",
        )
        self.assertEqual(suspend.status_code, 200)
        self.link.refresh_from_db()
        self.assertGreater(self.link.suspended_until, timezone.now())
        request = RequestFactory().get("/incident-link")
        request.user = AnonymousUser()
        self.assertEqual(redirecturl(request, "incident-link").status_code, 423)

        resume = self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "resume", "note": "Traffic verified"}),
            content_type="application/json",
        )
        self.assertEqual(resume.status_code, 200)
        self.link.refresh_from_db()
        self.assertIsNone(self.link.suspended_until)
        self.assertEqual(self.client.get("/incident-link").status_code, 302)

    def test_security_disable_is_reversible_without_affecting_unrelated_disabled_links(self):
        response = self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "disable"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertTrue(self.link.security_disabled)
        self.assertTrue(self.link.is_enabled)
        self.assertEqual(self.link.status_label, "Security blocked")

        self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "resume"}),
            content_type="application/json",
        )
        self.link.refresh_from_db()
        self.assertFalse(self.link.security_disabled)
        self.assertTrue(self.link.is_enabled)

        self.link.is_enabled = False
        self.link.save(update_fields=("is_enabled",))
        self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "disable"}),
            content_type="application/json",
        )
        self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "resume"}),
            content_type="application/json",
        )
        self.link.refresh_from_db()
        self.assertFalse(self.link.is_enabled)

    def test_expired_temporary_suspension_is_cleared(self):
        self.link.suspended_until = timezone.now() - timedelta(minutes=1)
        self.link.suspension_reason = "Expired test"
        self.link.save(update_fields=("suspended_until", "suspension_reason"))
        self.assertEqual(expire_link_suspensions(self.workspace), 1)
        self.link.refresh_from_db()
        self.assertIsNone(self.link.suspended_until)
        self.assertEqual(self.link.suspension_reason, "")

    def test_viewer_can_view_but_cannot_change_incident(self):
        viewer = User.objects.create_user("security-viewer", password="safe-password-123")
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=viewer,
            role=WorkspaceMembership.Role.VIEWER,
        )
        self.client.force_login(viewer)
        session = self.client.session
        session["workspace_id"] = self.workspace.pk
        session.save()
        self.assertEqual(self.client.get("/react/api/security/overview/").status_code, 200)
        response = self.client.post(
            f"/react/api/security/incidents/{self.incident.pk}/action/",
            data=json.dumps({"action": "resolve"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_update_security_settings(self):
        response = self.client.post(
            "/react/api/security/settings/",
            data=json.dumps({
                "monitoring_enabled": True,
                "sensitivity": "HIGH",
                "alert_threshold": 75,
                "email_alerts": False,
                "webhook_alerts": True,
                "automatic_throttling": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        settings = WorkspaceSecuritySettings.objects.get(workspace=self.workspace)
        self.assertEqual(settings.sensitivity, WorkspaceSecuritySettings.Sensitivity.HIGH)
        self.assertEqual(settings.alert_threshold, 75)
        self.assertTrue(settings.automatic_throttling)

    def test_security_settings_reject_string_booleans(self):
        response = self.client.post(
            "/react/api/security/settings/",
            data=json.dumps({"monitoring_enabled": "false"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("true or false", response.json()["error"])

    def test_cross_workspace_incident_is_not_exposed(self):
        other = User.objects.create_user("other-security-owner", password="safe-password-123")
        other_workspace = ensure_personal_workspace(other)
        other_link = urlModel.objects.create(
            workspace=other_workspace,
            owner=other,
            shorturl="private-incident-link",
            longurl="https://example.org/private",
        )
        other_incident = SecurityIncident.objects.create(
            workspace=other_workspace,
            link=other_link,
            threat_type=SecurityIncident.ThreatType.BOT_ACTIVITY,
            severity=SecurityIncident.Severity.HIGH,
            risk_score=70,
            explanation="Private tenant incident.",
        )
        request = RequestFactory().get(f"/react/api/security/incidents/{other_incident.pk}/")
        request.user = self.owner
        SessionMiddleware(lambda _request: None).process_request(request)
        request.session["workspace_id"] = self.workspace.pk
        with self.assertRaises(Http404):
            security_incident_detail(request, other_incident.pk)
