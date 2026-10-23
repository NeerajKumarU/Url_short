import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from .models import ClickEvent, urlModel


User = get_user_model()


class RoutingAndOperationsTests(TestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_returns_ready_when_db_is_up(self):
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})

    def test_metrics_exposes_prometheus_format(self):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app_requests_total")

    def test_admin_route_is_not_captured_as_an_alias(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_login_and_register_routes_load(self):
        self.assertEqual(self.client.get("/login/").status_code, 200)
        self.assertEqual(self.client.get("/register/").status_code, 200)

    def test_public_pages_include_persistent_theme_controls(self):
        response = self.client.get("/login/")
        self.assertContains(response, 'data-theme-toggle')
        self.assertContains(response, 'data-theme-label')
        self.assertContains(response, '>System</span>', html=False)
        self.assertContains(response, 'orbitlink-theme')
        self.assertContains(response, 'prefers-color-scheme: dark')


class AuthenticationTests(TestCase):
    def test_register_accepts_username_email_and_password(self):
        response = self.client.post(
            "/register/",
            {
                "username": "newuser",
                "email": "USER@Example.com",
                "password1": "a-secure-password-274!",
                "password2": "a-secure-password-274!",
            },
        )
        self.assertRedirects(response, "/dashboard/")
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "user@example.com")
        self.assertTrue(user.check_password("a-secure-password-274!"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user("existing", "user@example.com", "safe-password-123")
        response = self.client.post(
            "/register/",
            {
                "username": "newuser",
                "email": "USER@example.com",
                "password1": "a-secure-password-274!",
                "password2": "a-secure-password-274!",
            },
        )
        self.assertContains(response, "An account with this email already exists.")
        self.assertEqual(User.objects.count(), 1)

    def test_login_redirects_to_dashboard(self):
        User.objects.create_user("owner", password="safe-password-123")
        response = self.client.post(
            "/login/", {"username": "owner", "password": "safe-password-123"}
        )
        self.assertRedirects(response, "/dashboard/")

    def test_logout_redirects_home(self):
        user = User.objects.create_user("owner", password="safe-password-123")
        self.client.force_login(user)
        self.assertRedirects(self.client.post("/logout/"), "/login/")

    def test_dashboard_requires_authentication(self):
        self.assertRedirects(self.client.get("/dashboard/"), "/login/?next=/dashboard/")


class UrlShortenerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", "owner@example.com", "safe-password-123")
        self.client.force_login(self.user)

    def create(self, alias="", expires_at=""):
        return self.client.post(
            "/shorturl",
            {
                "longurl": "https://example.com/products/phone",
                "custom_alias": alias,
                "expires_at": expires_at,
            },
        )

    def test_home_page_loads(self):
        self.assertRedirects(self.client.get("/"), "/dashboard/")

    def test_anonymous_home_enters_login_experience(self):
        self.client.logout()
        self.assertRedirects(self.client.get("/"), "/login/")

    def test_create_link_page_uses_application_shell(self):
        response = self.client.get("/links/new/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application navigation")
        self.assertContains(response, "Create link")
        self.assertContains(response, "data-theme-toggle")

    def test_my_links_supports_search_and_pagination(self):
        urlModel.objects.bulk_create(
            [
                urlModel(
                    longurl=f"https://example.com/products/{index}",
                    shorturl=f"product-{index:02d}",
                    owner=self.user,
                )
                for index in range(21)
            ]
        )
        first_page = self.client.get("/links/")
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(len(first_page.context["page_obj"]), 20)
        self.assertContains(first_page, "Page 1 of 2")
        filtered = self.client.get("/links/", {"q": "product-20"})
        self.assertEqual(filtered.context["page_obj"].paginator.count, 1)
        self.assertContains(filtered, "/product-20")

    def test_custom_alias_is_created_and_owned(self):
        response = self.create("mobile-sale")
        self.assertEqual(response.status_code, 200)
        link = urlModel.objects.get()
        self.assertEqual(link.shorturl, "mobile-sale")
        self.assertEqual(link.owner, self.user)
        self.assertContains(response, "http://testserver/mobile-sale")

    def test_automatic_alias_generation_when_blank(self):
        response = self.create()
        self.assertEqual(response.status_code, 200)
        self.assertRegex(urlModel.objects.get().shorturl, re.compile(r"^[a-z0-9]{6}$"))

    def test_duplicate_alias_is_rejected(self):
        urlModel.objects.create(longurl="https://first.example", shorturl="mobile-sale")
        response = self.create("mobile-sale")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "This alias is already taken.", status_code=400)
        self.assertEqual(urlModel.objects.count(), 1)

    def test_invalid_alias_characters_are_rejected(self):
        response = self.create("not valid!")
        self.assertContains(
            response,
            "only letters, numbers, hyphens, or underscores",
            status_code=400,
        )

    def test_uppercase_alias_is_normalized(self):
        self.create("Mobile-SALE")
        self.assertEqual(urlModel.objects.get().shorturl, "mobile-sale")

    def test_reserved_alias_is_rejected(self):
        response = self.create("admin")
        self.assertContains(response, "This alias is reserved", status_code=400)

    def test_anonymous_user_cannot_create(self):
        self.client.logout()
        response = self.create("mobile-sale")
        self.assertRedirects(response, "/login/?next=/shorturl")
        self.assertFalse(urlModel.objects.exists())

    def test_csrf_is_required_for_creation(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            "/shorturl", {"longurl": "https://example.com", "custom_alias": "secure-link"}
        )
        self.assertEqual(response.status_code, 403)


class ExpiryAndManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="safe-password-123")
        self.other = User.objects.create_user("other", password="safe-password-123")
        self.client.force_login(self.user)

    def test_active_link_redirects(self):
        link = urlModel.objects.create(
            longurl="https://example.com",
            shorturl="active-link",
            owner=self.user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get(f"/{link.shorturl}")
        self.assertRedirects(response, "https://example.com", fetch_redirect_response=False)

    def test_expired_link_returns_410_without_counting_click(self):
        link = urlModel.objects.create(
            longurl="https://example.com",
            shorturl="expired-link",
            owner=self.user,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(f"/{link.shorturl}")
        self.assertContains(response, "This link has expired.", status_code=410)
        link.refresh_from_db()
        self.assertEqual(link.count, 0)
        self.assertFalse(ClickEvent.objects.exists())

    def test_past_expiry_is_rejected_when_creating(self):
        past = timezone.localtime(timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            "/shorturl",
            {"longurl": "https://example.com", "custom_alias": "past-link", "expires_at": past},
        )
        self.assertContains(response, "Expiry must be a future date and time.", status_code=400)
        self.assertFalse(urlModel.objects.exists())

    def test_owner_can_edit_destination_and_expiry(self):
        link = urlModel.objects.create(
            longurl="https://old.example", shorturl="stable-link", owner=self.user
        )
        future = timezone.localtime(timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            f"/links/{link.pk}/edit/",
            {"longurl": "https://new.example", "expires_at": future},
        )
        self.assertRedirects(response, "/dashboard/")
        link.refresh_from_db()
        self.assertEqual(link.longurl, "https://new.example")
        self.assertEqual(link.shorturl, "stable-link")
        self.assertIsNotNone(link.expires_at)

    def test_user_cannot_edit_or_delete_another_users_link(self):
        link = urlModel.objects.create(
            longurl="https://example.com", shorturl="private-link", owner=self.other
        )
        self.assertEqual(self.client.get(f"/links/{link.pk}/edit/").status_code, 404)
        self.assertEqual(self.client.post(f"/links/{link.pk}/delete/").status_code, 404)
        self.assertTrue(urlModel.objects.filter(pk=link.pk).exists())

    def test_dashboard_lists_only_current_users_links(self):
        urlModel.objects.create(longurl="https://mine.example", shorturl="mine-link", owner=self.user)
        urlModel.objects.create(longurl="https://other.example", shorturl="other-link", owner=self.other)
        response = self.client.get("/dashboard/")
        self.assertContains(response, "mine-link")
        self.assertNotContains(response, "other-link")


class QrAndAnalyticsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", password="safe-password-123")
        self.client.force_login(self.user)
        self.link = urlModel.objects.create(
            longurl="https://example.com", shorturl="campaign", owner=self.user
        )

    def test_qr_code_is_generated_as_png(self):
        response = self.client.get(f"/links/{self.link.pk}/qr/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    @patch("url_short.views.qrcode.make")
    def test_qr_encodes_the_short_url_not_the_destination(self, make_qr):
        make_qr.return_value.save.side_effect = lambda output, format: output.write(b"PNG")
        self.client.get(f"/links/{self.link.pk}/qr/")
        make_qr.assert_called_once_with("http://testserver/campaign")

    def test_qr_code_is_owner_only(self):
        other = User.objects.create_user("other", password="safe-password-123")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/links/{self.link.pk}/qr/").status_code, 404)

    def test_successful_click_creates_event_and_increments_count(self):
        self.client.get("/campaign")
        self.client.get("/campaign")
        self.link.refresh_from_db()
        self.assertEqual(self.link.count, 2)
        self.assertEqual(ClickEvent.objects.filter(short_url=self.link).count(), 2)

    def test_headers_are_classified_and_referrer_is_captured(self):
        response = self.client.get(
            "/campaign",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) Chrome/124.0 Safari/537.36",
            HTTP_REFERER="https://www.google.com/search?q=orbit",
            REMOTE_ADDR="203.0.113.10",
        )
        self.assertEqual(response.status_code, 302)
        event = ClickEvent.objects.get()
        self.assertEqual(event.browser, "Chrome")
        self.assertEqual(event.device_type, "Desktop")
        self.assertEqual(event.operating_system, "Windows")
        self.assertEqual(event.referrer_source, "Google")
        self.assertEqual(event.ip_address, "203.0.113.10")
        self.assertEqual(event.referrer, "https://www.google.com/search?q=orbit")

    def test_missing_headers_are_handled_safely(self):
        self.client.get("/campaign", REMOTE_ADDR="not-an-ip")
        event = ClickEvent.objects.get()
        self.assertEqual(event.browser, "Other")
        self.assertEqual(event.device_type, "Other")
        self.assertEqual(event.operating_system, "Other")
        self.assertEqual(event.referrer_source, "Direct")
        self.assertIsNone(event.ip_address)

    def test_dashboard_uses_real_analytics_data(self):
        self.client.get("/campaign", HTTP_USER_AGENT="Mozilla/5.0 Firefox/120.0")
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Total clicks")
        self.assertContains(response, "Firefox")
        self.assertContains(response, "/campaign")

    def test_unknown_short_url_returns_404(self):
        self.assertEqual(self.client.get("/doesnotexist").status_code, 404)
