from django.contrib.auth import get_user_model
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import AuditLog, Campaign, WorkspaceMembership, WebhookEndpoint, urlModel
from .services import ensure_personal_workspace


User = get_user_model()


class WorkspaceAndRbacTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="safe-password-123")
        self.member = User.objects.create_user("member", password="safe-password-123")
        self.outsider = User.objects.create_user("outsider", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)

    def add_member(self, role):
        return WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.member,
            role=role,
        )

    def test_owner_membership_is_created_once(self):
        ensure_personal_workspace(self.owner)
        membership = WorkspaceMembership.objects.get(
            workspace=self.workspace,
            user=self.owner,
        )
        self.assertEqual(membership.role, WorkspaceMembership.Role.OWNER)
        self.assertEqual(WorkspaceMembership.objects.filter(user=self.owner).count(), 1)

    def test_duplicate_membership_is_rejected(self):
        self.add_member(WorkspaceMembership.Role.VIEWER)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_member(WorkspaceMembership.Role.EDITOR)

    def test_viewer_can_read_dashboard_but_cannot_create_link(self):
        self.add_member(WorkspaceMembership.Role.VIEWER)
        session = self.client.session
        session["workspace_id"] = self.workspace.pk
        session.save()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)
        response = self.client.post(
            "/shorturl",
            {"longurl": "https://example.com", "custom_alias": "viewer-link"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(urlModel.objects.filter(shorturl="viewer-link").exists())

    def test_editor_creates_link_in_selected_workspace_and_audit_event(self):
        self.add_member(WorkspaceMembership.Role.EDITOR)
        session = self.client.session
        session["workspace_id"] = self.workspace.pk
        session.save()
        self.client.force_login(self.member)
        response = self.client.post(
            "/shorturl",
            {"longurl": "https://example.com", "custom_alias": "editor-link"},
        )
        self.assertEqual(response.status_code, 200)
        link = urlModel.objects.get(shorturl="editor-link")
        self.assertEqual(link.workspace, self.workspace)
        self.assertEqual(link.owner, self.member)
        self.assertTrue(
            AuditLog.objects.filter(
                workspace=self.workspace,
                actor=self.member,
                action="LINK_CREATED",
                target_id=str(link.pk),
            ).exists()
        )

    def test_outsider_cannot_select_workspace(self):
        self.client.force_login(self.outsider)
        response = self.client.post(f"/workspaces/{self.workspace.slug}/switch/")
        self.assertEqual(response.status_code, 404)

    def test_workspace_switch_does_not_allow_external_redirect(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/workspaces/{self.workspace.slug}/switch/",
            {"next": "https://evil.example/phishing"},
        )
        self.assertRedirects(response, "/dashboard/")


class CampaignAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="safe-password-123")
        self.other = User.objects.create_user("other", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.other_workspace = ensure_personal_workspace(self.other)
        self.client.force_login(self.owner)

    def test_campaign_is_created_in_current_workspace(self):
        response = self.client.post(
            "/campaigns/new/",
            {"name": "Launch", "description": "Q4", "status": Campaign.Status.ACTIVE},
        )
        self.assertRedirects(response, "/campaigns/")
        campaign = Campaign.objects.get(name="Launch")
        self.assertEqual(campaign.workspace, self.workspace)
        self.assertEqual(campaign.created_by, self.owner)

    def test_campaign_from_another_workspace_is_not_editable(self):
        campaign = Campaign.objects.create(
            workspace=self.other_workspace,
            created_by=self.other,
            name="Private",
        )
        self.assertEqual(self.client.get(f"/campaigns/{campaign.pk}/edit/").status_code, 404)

    def test_campaign_list_includes_workspace_analytics(self):
        campaign = Campaign.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            name="Measured launch",
        )
        urlModel.objects.create(
            workspace=self.workspace,
            owner=self.owner,
            campaign=campaign,
            shorturl="measured",
            longurl="https://example.com",
            count=7,
        )
        response = self.client.get("/campaigns/")
        row = next(item for item in response.context["campaigns"] if item.pk == campaign.pk)
        self.assertEqual(row.link_count, 1)
        self.assertEqual(row.click_count, 7)


class PlatformAdminDashboardTests(TestCase):
    def test_normal_user_is_denied(self):
        user = User.objects.create_user("normal", password="safe-password-123")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/admin-dashboard/").status_code, 403)

    def test_workspace_admin_is_not_a_platform_admin(self):
        owner = User.objects.create_user("workspace-owner", password="safe-password-123")
        member = User.objects.create_user("workspace-admin", password="safe-password-123")
        workspace = ensure_personal_workspace(owner)
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=member,
            role=WorkspaceMembership.Role.ADMIN,
        )
        self.client.force_login(member)
        self.assertEqual(self.client.get("/admin-dashboard/").status_code, 403)

    def test_staff_user_can_view_operations_dashboard(self):
        staff = User.objects.create_user(
            "operator",
            password="safe-password-123",
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get("/admin-dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations dashboard")
        self.assertContains(response, "Platform overview")

    def test_system_health_is_staff_only_and_reports_verified_checks(self):
        normal = User.objects.create_user("health-normal", password="safe-password-123")
        self.client.force_login(normal)
        self.assertEqual(self.client.get("/admin-dashboard/system-health/").status_code, 403)
        staff = User.objects.create_user(
            "health-operator", password="safe-password-123", is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get("/admin-dashboard/system-health/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System health")
        self.assertContains(response, "Database")
        self.assertContains(response, "No Kafka runtime is configured")

    def test_normal_sidebar_hides_platform_navigation(self):
        user = User.objects.create_user("sidebar-user", password="safe-password-123")
        self.client.force_login(user)
        response = self.client.get("/dashboard/")
        self.assertNotContains(response, "Platform overview")
        self.assertContains(response, "Create link")

    def test_modern_admin_keeps_registered_models_available(self):
        superuser = User.objects.create_superuser(
            "root-admin",
            "root@example.com",
            "safe-password-123",
        )
        self.client.force_login(superuser)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform control center")
        self.assertContains(response, "Webhook deliveries")
        self.assertIn(urlModel, admin.site._registry)
        self.assertIn(WebhookEndpoint, admin.site._registry)

    def test_admin_login_uses_orbitlink_branding(self):
        response = self.client.get("/admin/login/")
        self.assertContains(response, "Administrator sign in")

    def test_user_detail_is_staff_only(self):
        target = User.objects.create_user("detail-target", password="safe-password-123")
        normal = User.objects.create_user("detail-normal", password="safe-password-123")
        self.client.force_login(normal)
        self.assertEqual(self.client.get(f"/admin-dashboard/users/{target.pk}/").status_code, 403)
        staff = User.objects.create_user("detail-staff", password="safe-password-123", is_staff=True)
        self.client.force_login(staff)
        self.assertContains(self.client.get(f"/admin-dashboard/users/{target.pk}/"), "detail-target")

    def test_staff_status_action_is_audited(self):
        staff = User.objects.create_user("operator", password="safe-password-123", is_staff=True)
        target = User.objects.create_user("target", password="safe-password-123")
        self.client.force_login(staff)
        response = self.client.post(
            f"/admin-dashboard/users/{target.pk}/status/",
            {"action": "disable"},
        )
        self.assertRedirects(response, "/admin-dashboard/")
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(
            AuditLog.objects.filter(action="USER_DISABLED", target_id=str(target.pk)).exists()
        )
