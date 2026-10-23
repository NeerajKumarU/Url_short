from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import AbuseReport, ApprovalRequest, AuditLog, ClickEvent, WorkspaceMembership, urlModel
from .services import ensure_personal_workspace


User = get_user_model()


class SecurityAndBotDetectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("security-owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.user)
        self.link = urlModel.objects.create(
            owner=self.user,
            workspace=self.workspace,
            shorturl="security-link",
            longurl="https://example.com/destination",
        )

    def test_private_destination_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/shorturl",
            {"longurl": "http://127.0.0.1/admin", "custom_alias": "private-target"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Private, loopback", status_code=400)
        self.assertFalse(urlModel.objects.filter(shorturl="private-target").exists())

    def test_known_bot_is_classified_on_redirect(self):
        response = self.client.get(
            "/security-link",
            HTTP_USER_AGENT="Mozilla/5.0 (compatible; Googlebot/2.1)",
        )
        self.assertEqual(response.status_code, 302)
        click = ClickEvent.objects.get(short_url=self.link)
        self.assertEqual(click.bot_classification, ClickEvent.BotClassification.KNOWN_BOT)
        self.assertIn("googlebot", click.bot_reason)

    def test_confirmed_malicious_link_is_blocked_without_click(self):
        self.link.safety_status = urlModel.SafetyStatus.MALICIOUS
        self.link.safety_detail = "Confirmed by platform operator"
        self.link.save(update_fields=("safety_status", "safety_detail"))
        response = self.client.get("/security-link")
        self.assertEqual(response.status_code, 451)
        self.assertEqual(ClickEvent.objects.filter(short_url=self.link).count(), 0)
        self.link.refresh_from_db()
        self.assertEqual(self.link.count, 0)

    def test_dashboard_can_filter_human_and_bot_traffic(self):
        ClickEvent.objects.create(
            short_url=self.link,
            bot_classification=ClickEvent.BotClassification.HUMAN,
        )
        ClickEvent.objects.create(
            short_url=self.link,
            bot_classification=ClickEvent.BotClassification.LIKELY_BOT,
        )
        self.client.force_login(self.user)
        response = self.client.get("/dashboard/?traffic=bot")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtered_clicks"], 1)
        self.assertEqual(response.context["human_clicks"], 1)
        self.assertEqual(response.context["bot_clicks"], 1)


class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("approval-owner", password="safe-password-123")
        self.editor = User.objects.create_user("approval-editor", password="safe-password-123")
        self.viewer = User.objects.create_user("approval-viewer", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.workspace.require_link_approval = True
        self.workspace.save(update_fields=("require_link_approval",))
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.editor,
            role=WorkspaceMembership.Role.EDITOR,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.viewer,
            role=WorkspaceMembership.Role.VIEWER,
        )

    def select_workspace(self):
        session = self.client.session
        session["workspace_id"] = self.workspace.pk
        session.save()

    def test_editor_link_requires_admin_approval_before_redirect(self):
        self.client.force_login(self.editor)
        self.select_workspace()
        response = self.client.post(
            "/shorturl",
            {"longurl": "https://example.com/approved", "custom_alias": "needs-approval"},
        )
        self.assertEqual(response.status_code, 200)
        link = urlModel.objects.get(shorturl="needs-approval")
        self.assertEqual(link.approval_status, urlModel.ApprovalStatus.DRAFT)
        self.assertEqual(self.client.get("/needs-approval").status_code, 404)

        response = self.client.post(f"/links/{link.pk}/submit-approval/", {"comment": "Ready"})
        self.assertRedirects(response, "/dashboard/")
        approval = ApprovalRequest.objects.get(link=link)
        link.refresh_from_db()
        self.assertEqual(link.approval_status, urlModel.ApprovalStatus.PENDING_APPROVAL)

        self.client.force_login(self.viewer)
        self.select_workspace()
        self.assertEqual(
            self.client.post(
                f"/approvals/{approval.pk}/review/",
                {"decision": "approve"},
            ).status_code,
            403,
        )

        self.client.force_login(self.owner)
        self.select_workspace()
        response = self.client.post(
            f"/approvals/{approval.pk}/review/",
            {"decision": "approve", "comment": "Approved"},
        )
        self.assertRedirects(response, "/approvals/")
        link.refresh_from_db()
        approval.refresh_from_db()
        self.assertEqual(link.approval_status, urlModel.ApprovalStatus.APPROVED)
        self.assertEqual(approval.reviewer, self.owner)
        self.assertEqual(self.client.get("/needs-approval").status_code, 302)
        self.assertTrue(
            AuditLog.objects.filter(action="APPROVAL_GRANTED", target_id=str(link.pk)).exists()
        )


class AbuseReportWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("report-owner", password="safe-password-123")
        self.staff = User.objects.create_user(
            "report-staff",
            password="safe-password-123",
            is_staff=True,
        )
        self.workspace = ensure_personal_workspace(self.owner)
        self.link = urlModel.objects.create(
            owner=self.owner,
            workspace=self.workspace,
            shorturl="reported-link",
            longurl="https://example.com",
        )

    def test_public_report_can_be_actioned_by_platform_staff(self):
        response = self.client.post(
            "/report/reported-link/",
            {
                "reason": AbuseReport.Reason.PHISHING,
                "details": "This page impersonates another service.",
                "reporter_email": "reporter@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        report = AbuseReport.objects.get(link=self.link)
        self.assertEqual(report.status, AbuseReport.Status.OPEN)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/admin-dashboard/reports/").status_code, 403)

        self.client.force_login(self.staff)
        response = self.client.post(
            f"/admin-dashboard/reports/{report.pk}/action/",
            {"action": "disable", "resolution": "Confirmed phishing"},
        )
        self.assertRedirects(response, "/admin-dashboard/reports/")
        report.refresh_from_db()
        self.link.refresh_from_db()
        self.assertEqual(report.status, AbuseReport.Status.ACTIONED)
        self.assertFalse(self.link.is_enabled)
        self.assertEqual(self.link.approval_status, urlModel.ApprovalStatus.DISABLED)
        self.assertEqual(self.client.get("/reported-link").status_code, 404)
