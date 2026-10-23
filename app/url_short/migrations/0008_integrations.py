from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("url_short", "0007_security_governance"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebhookEndpoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("endpoint_url", models.URLField(max_length=2048)),
                ("secret_seed", models.CharField(editable=False, max_length=128)),
                ("secret_prefix", models.CharField(editable=False, max_length=16)),
                ("subscribed_events", models.JSONField(default=list)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_webhooks", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webhook_endpoints", to="url_short.workspace")),
            ],
            options={"ordering": ("name", "pk")},
        ),
        migrations.CreateModel(
            name="WebhookDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=48)),
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("SUCCEEDED", "Succeeded"), ("FAILED", "Failed"), ("RETRYING", "Retrying")], db_index=True, default="PENDING", max_length=12)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("response_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.CharField(blank=True, max_length=1000)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("next_retry_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("endpoint", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="url_short.webhookendpoint")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ApiCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("prefix", models.CharField(db_index=True, max_length=20, unique=True)),
                ("key_hash", models.CharField(editable=False, max_length=255)),
                ("scopes", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_api_credentials", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_credentials", to="url_short.workspace")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="webhookendpoint",
            index=models.Index(fields=["workspace", "is_active"], name="url_short_w_workspa_b78a50_idx"),
        ),
        migrations.AddIndex(
            model_name="webhookdelivery",
            index=models.Index(fields=["status", "next_retry_at"], name="url_short_w_status_7b43c3_idx"),
        ),
        migrations.AddIndex(
            model_name="apicredential",
            index=models.Index(fields=["workspace", "revoked_at"], name="url_short_a_workspa_66cae2_idx"),
        ),
    ]
