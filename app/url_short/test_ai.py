from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .ai import AIResult, build_workspace_analytics_context
from .models import Campaign, ClickEvent, WorkspaceMembership, urlModel
from .services import ensure_personal_workspace


User = get_user_model()


class CapturingProvider:
    available = True

    def __init__(self):
        self.context = None

    def complete(self, *, system_prompt, user_prompt, context):
        self.context = context
        return AIResult(True, text="Authorized answer")


class AIAnalyticsIsolationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("ai-owner", password="safe-password-123")
        self.other = User.objects.create_user("ai-other", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.other_workspace = ensure_personal_workspace(self.other)
        self.link = urlModel.objects.create(workspace=self.workspace, owner=self.owner, shorturl="visible-ai-link", longurl="https://example.com")
        self.other_link = urlModel.objects.create(workspace=self.other_workspace, owner=self.other, shorturl="secret-other-link", longurl="https://example.org")
        ClickEvent.objects.create(short_url=self.link)
        ClickEvent.objects.create(short_url=self.other_link)

    def test_structured_retrieval_never_contains_another_workspace(self):
        context = build_workspace_analytics_context(self.workspace)
        aliases = {row["shorturl"] for row in context["links"]}
        self.assertIn("visible-ai-link", aliases)
        self.assertNotIn("secret-other-link", aliases)
        self.assertEqual(context["workspace"], self.workspace.name)

    @override_settings(ORBITLINK_AI_API_KEY="")
    def test_missing_provider_is_explicit_and_nonfatal(self):
        self.client.force_login(self.owner)
        response = self.client.get("/ai/analytics/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI is unavailable")

    def test_assistant_receives_only_selected_workspace_context(self):
        provider = CapturingProvider()
        self.client.force_login(self.owner)
        with patch("url_short.ai_views.get_ai_provider", return_value=provider):
            response = self.client.post("/ai/analytics/", {"question": "Best link?"})
        self.assertContains(response, "Authorized answer")
        aliases = {row["shorturl"] for row in provider.context["links"]}
        self.assertEqual(aliases, {"visible-ai-link"})


class AIAdminAndSuggestionTests(TestCase):
    def test_abuse_assistant_is_platform_admin_only(self):
        normal = User.objects.create_user("not-staff", password="safe-password-123")
        self.client.force_login(normal)
        self.assertEqual(self.client.get("/admin-dashboard/ai-abuse/").status_code, 403)

    def test_campaign_suggestions_do_not_create_campaigns(self):
        owner = User.objects.create_user("suggest-owner", password="safe-password-123")
        workspace = ensure_personal_workspace(owner)
        provider = CapturingProvider()
        self.client.force_login(owner)
        with patch("url_short.ai_views.get_ai_provider", return_value=provider):
            response = self.client.post("/ai/campaign-suggestions/", {"brief": "Launch a mobile app"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suggestions—not applied")
        self.assertEqual(Campaign.objects.filter(workspace=workspace).count(), 0)
