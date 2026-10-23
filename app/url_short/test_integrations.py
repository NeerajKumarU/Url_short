import hashlib
import hmac
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from .api_keys import authenticate_api_key, create_api_credential
from .models import ApiCredential, WebhookDelivery, urlModel
from .services import ensure_personal_workspace
from .webhooks import (
    create_webhook_endpoint,
    queue_webhook_event,
    serialize_webhook_payload,
    signature_for_delivery,
)


User = get_user_model()


class ApiCredentialTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("api-owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)

    def test_raw_key_is_not_stored_and_authentication_updates_usage(self):
        credential, raw_key = create_api_credential(
            workspace=self.workspace,
            name="Automation",
            scopes=["links:read"],
            created_by=self.owner,
        )
        self.assertNotEqual(credential.key_hash, raw_key)
        self.assertNotIn(raw_key, credential.key_hash)
        authenticated, error = authenticate_api_key(raw_key, "links:read")
        self.assertIsNone(error)
        self.assertEqual(authenticated, credential)
        credential.refresh_from_db()
        self.assertIsNotNone(credential.last_used_at)

    def test_revoked_key_is_rejected_and_scope_is_enforced(self):
        credential, raw_key = create_api_credential(
            workspace=self.workspace,
            name="Read only",
            scopes=["links:read"],
            created_by=self.owner,
        )
        response = self.client.post(
            "/api/v1/links/",
            data='{"destination":"https://example.com","alias":"api-created"}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(urlModel.objects.filter(shorturl="api-created").exists())

        from django.utils import timezone

        credential.revoked_at = timezone.now()
        credential.save(update_fields=("revoked_at",))
        response = self.client.get(
            "/api/v1/links/",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 401)

    def test_write_scoped_key_creates_link_in_its_workspace(self):
        _, raw_key = create_api_credential(
            workspace=self.workspace,
            name="Writer",
            scopes=["links:write"],
            created_by=self.owner,
        )
        response = self.client.post(
            "/api/v1/links/",
            data='{"destination":"https://example.com/api","alias":"api-created"}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(urlModel.objects.get(shorturl="api-created").workspace, self.workspace)


class WebhookTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("hook-owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)

    def test_delivery_signature_matches_once_revealed_secret(self):
        endpoint, raw_secret = create_webhook_endpoint(
            workspace=self.workspace,
            name="Events",
            endpoint_url="https://hooks.example.com/orbitlink",
            subscribed_events=["LINK_CREATED"],
            created_by=self.owner,
        )
        delivery = queue_webhook_event(
            self.workspace,
            "LINK_CREATED",
            {"link_id": 42, "alias": "launch"},
        )[0]
        expected = hmac.new(
            raw_secret.encode("utf-8"),
            serialize_webhook_payload(delivery),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(signature_for_delivery(delivery), expected)
        self.assertNotEqual(endpoint.secret_seed, raw_secret)
        self.assertFalse(hasattr(endpoint, "secret"))

    def test_disabled_or_unsubscribed_hooks_are_ignored(self):
        endpoint, _ = create_webhook_endpoint(
            workspace=self.workspace,
            name="Disabled",
            endpoint_url="https://hooks.example.com/orbitlink",
            subscribed_events=["LINK_CREATED"],
            created_by=self.owner,
            is_active=False,
        )
        queue_webhook_event(self.workspace, "LINK_CREATED", {"link_id": 1})
        self.assertFalse(WebhookDelivery.objects.filter(endpoint=endpoint).exists())

    @patch("url_short.management.commands.process_operations.deliver_webhook")
    def test_operations_job_attempts_new_pending_deliveries(self, deliver):
        create_webhook_endpoint(
            workspace=self.workspace,
            name="Scheduled",
            endpoint_url="https://hooks.example.com/orbitlink",
            subscribed_events=["LINK_CREATED"],
            created_by=self.owner,
        )
        delivery = queue_webhook_event(self.workspace, "LINK_CREATED", {"link_id": 7})[0]
        call_command("process_operations")
        deliver.assert_called_once()
        self.assertEqual(deliver.call_args.args[0].pk, delivery.pk)


class BulkImportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("import-owner", password="safe-password-123")
        self.workspace = ensure_personal_workspace(self.owner)
        self.client.force_login(self.owner)

    def test_invalid_row_reports_error_and_imports_nothing(self):
        upload = SimpleUploadedFile(
            "links.csv",
            b"destination,alias\nhttps://example.com,valid-row\nhttp://127.0.0.1/private,bad-row\n",
            content_type="text/csv",
        )
        response = self.client.post("/tools/bulk-import/", {"csv_file": upload})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing was imported")
        self.assertFalse(urlModel.objects.filter(shorturl__in=("valid-row", "bad-row")).exists())

    def test_valid_csv_imports_links_atomically(self):
        upload = SimpleUploadedFile(
            "links.csv",
            b"destination,alias\nhttps://example.com/one,first-row\nhttps://example.com/two,second-row\n",
            content_type="text/csv",
        )
        response = self.client.post("/tools/bulk-import/", {"csv_file": upload})
        self.assertRedirects(response, "/dashboard/")
        self.assertEqual(
            urlModel.objects.filter(workspace=self.workspace, shorturl__in=("first-row", "second-row")).count(),
            2,
        )
