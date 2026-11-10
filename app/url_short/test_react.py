from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import TestCase

from .models import ClickEvent, urlModel


User = get_user_model()


class ReactMigrationAdapterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "react-owner",
            "react@example.com",
            "safe-password-123",
        )
        self.client.force_login(self.user)

    def test_react_shell_supports_deep_links(self):
        response = self.client.get("/react/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="root"')
        self.assertContains(response, static("react/app.js"))

    def test_bootstrap_requires_authentication(self):
        self.client.logout()
        response = self.client.get("/react/api/bootstrap/")
        self.assertRedirects(
            response,
            "/login/?next=/react/api/bootstrap/",
            fetch_redirect_response=False,
        )

    def test_dashboard_adapter_returns_real_workspace_data(self):
        link = urlModel.objects.create(
            longurl="https://example.com/react",
            shorturl="react-link",
            owner=self.user,
            count=4,
        )
        ClickEvent.objects.create(short_url=link, browser="Firefox", device_type="Desktop")
        response = self.client.get("/react/api/bootstrap/", {"_view": "dashboard"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["shell"]["user"]["username"], "react-owner")
        self.assertEqual(payload["page"]["total_links"], 1)
        self.assertEqual(payload["page"]["total_clicks"], 4)
        self.assertEqual(payload["page"]["top_links"][0]["alias"], "react-link")

    def test_links_adapter_filters_and_never_exposes_other_users_links(self):
        urlModel.objects.create(longurl="https://example.com/keep", shorturl="keep-me", owner=self.user)
        other = User.objects.create_user("other", password="safe-password-123")
        urlModel.objects.create(longurl="https://example.com/private", shorturl="private", owner=other)
        response = self.client.get(
            "/react/api/bootstrap/",
            {"_view": "links", "q": "keep"},
        )
        self.assertEqual(response.status_code, 200)
        links = response.json()["page"]["links"]
        self.assertEqual([link["alias"] for link in links], ["keep-me"])

    def test_unknown_react_view_is_rejected(self):
        response = self.client.get("/react/api/bootstrap/", {"_view": "not-real"})
        self.assertEqual(response.status_code, 404)

    def test_every_migrated_page_returns_authorized_real_data(self):
        urlModel.objects.create(
            longurl="https://example.com/all-pages",
            shorturl="all-pages",
            owner=self.user,
        )
        for view_name in (
            "links",
            "analytics",
            "audience",
            "campaigns",
            "qr-codes",
            "settings",
        ):
            with self.subTest(view_name=view_name):
                response = self.client.get(
                    "/react/api/bootstrap/",
                    {"_view": view_name},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("shell", payload)
                self.assertIn("page", payload)
