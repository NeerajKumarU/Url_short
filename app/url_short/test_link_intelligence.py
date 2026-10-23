from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .link_services import build_utm_url, create_link_version, rollback_link
from .models import (
    ClickEvent,
    CustomDomain,
    LinkVersion,
    RedirectRule,
    WorkspaceMembership,
    urlModel,
)
from .services import ensure_personal_workspace


User = get_user_model()


class CustomDomainTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="safe-password-123")
        self.other = User.objects.create_user("other", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.other_workspace = ensure_personal_workspace(self.other)

    def test_domain_is_normalized_and_starts_pending(self):
        domain = CustomDomain.objects.create(workspace=self.workspace, domain="Go.Example.COM.")
        self.assertEqual(domain.domain, "go.example.com")
        self.assertEqual(domain.verification_status, CustomDomain.VerificationStatus.PENDING)
        self.assertTrue(domain.verification_token)

    def test_domain_cannot_be_claimed_by_multiple_workspaces(self):
        CustomDomain.objects.create(workspace=self.workspace, domain="go.example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomDomain.objects.create(workspace=self.other_workspace, domain="GO.EXAMPLE.COM")

    def test_editor_cannot_add_domain(self):
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.other,
            role=WorkspaceMembership.Role.EDITOR,
        )
        self.client.force_login(self.other)
        session = self.client.session
        session["workspace_id"] = self.workspace.pk
        session.save()
        response = self.client.post("/domains/new/", {"domain": "go.example.com"})
        self.assertEqual(response.status_code, 403)


class SmartRoutingTests(TestCase):
    def setUp(self):
        self.link = urlModel.objects.create(
            shorturl="smart-link",
            longurl="https://fallback.example",
        )

    def test_device_rule_routes_mobile_and_attributes_click(self):
        rule = RedirectRule.objects.create(
            link=self.link,
            name="Mobile",
            condition_type=RedirectRule.ConditionType.DEVICE,
            match_value="Mobile",
            destination_url="https://mobile.example",
            priority=10,
        )
        response = self.client.get(
            "/smart-link",
            HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14) Mobile Chrome/124.0",
        )
        self.assertRedirects(response, "https://mobile.example", fetch_redirect_response=False)
        event = ClickEvent.objects.get()
        self.assertEqual(event.routing_rule, rule)
        self.assertEqual(event.resolved_destination, "https://mobile.example")

    def test_country_rule_uses_cloudflare_country_signal(self):
        RedirectRule.objects.create(
            link=self.link,
            name="India",
            condition_type=RedirectRule.ConditionType.COUNTRY,
            match_value="IN, SG",
            destination_url="https://in.example",
            priority=10,
        )
        response = self.client.get("/smart-link", HTTP_CF_IPCOUNTRY="IN")
        self.assertRedirects(response, "https://in.example", fetch_redirect_response=False)

    def test_unmatched_request_uses_default_rule_then_link_fallback(self):
        RedirectRule.objects.create(
            link=self.link,
            name="Default",
            condition_type=RedirectRule.ConditionType.DEFAULT,
            destination_url="https://rule-fallback.example",
            priority=999,
        )
        response = self.client.get("/smart-link")
        self.assertRedirects(
            response,
            "https://rule-fallback.example",
            fetch_redirect_response=False,
        )


class SchedulingAndVersioningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.user)

    def test_link_before_activation_does_not_redirect_or_count(self):
        link = urlModel.objects.create(
            workspace=self.workspace,
            owner=self.user,
            shorturl="scheduled-link",
            longurl="https://example.com",
            active_from=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get("/scheduled-link")
        self.assertEqual(response.status_code, 404)
        link.refresh_from_db()
        self.assertEqual(link.count, 0)
        self.assertFalse(ClickEvent.objects.exists())

    def test_disabled_link_does_not_redirect(self):
        urlModel.objects.create(
            workspace=self.workspace,
            owner=self.user,
            shorturl="disabled-link",
            longurl="https://example.com",
            is_enabled=False,
        )
        self.assertEqual(self.client.get("/disabled-link").status_code, 404)

    def test_rollback_restores_snapshot_and_creates_new_version(self):
        link = urlModel.objects.create(
            workspace=self.workspace,
            owner=self.user,
            shorturl="versioned-link",
            longurl="https://one.example",
        )
        first = create_link_version(link, self.user, "Initial")
        link.longurl = "https://two.example"
        link.save(update_fields=("longurl", "updated_at"))
        create_link_version(link, self.user, "Destination changed")
        created = rollback_link(link, first, self.user)
        link.refresh_from_db()
        self.assertEqual(link.longurl, "https://one.example")
        self.assertEqual(created.version_number, 3)
        self.assertEqual(LinkVersion.objects.filter(link=link).count(), 3)


class UtmBuilderTests(TestCase):
    def test_preserves_query_and_replaces_existing_utm_values(self):
        result = build_utm_url(
            "https://example.com/page?item=42&utm_source=old#details",
            {
                "utm_source": "newsletter",
                "utm_medium": "email campaign",
                "utm_campaign": "launch",
            },
        )
        self.assertIn("item=42", result)
        self.assertIn("utm_source=newsletter", result)
        self.assertIn("utm_medium=email+campaign", result)
        self.assertEqual(result.count("utm_source="), 1)
        self.assertTrue(result.endswith("#details"))
