from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("url_short", "0006_experiments_and_conversions"),
    ]

    operations = [
        migrations.AddField(
            model_name="clickevent",
            name="bot_classification",
            field=models.CharField(
                choices=[
                    ("HUMAN", "Human"),
                    ("KNOWN_BOT", "Known bot"),
                    ("LIKELY_BOT", "Likely bot"),
                    ("UNKNOWN", "Unknown"),
                ],
                db_index=True,
                default="UNKNOWN",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="clickevent",
            name="bot_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING_APPROVAL", "Pending approval"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("DISABLED", "Disabled"),
                ],
                db_index=True,
                default="APPROVED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="safety_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="safety_detail",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="safety_status",
            field=models.CharField(
                choices=[
                    ("SAFE", "Safe"),
                    ("SUSPICIOUS", "Suspicious"),
                    ("MALICIOUS", "Malicious"),
                    ("UNKNOWN", "Unknown"),
                    ("PENDING", "Pending"),
                ],
                db_index=True,
                default="UNKNOWN",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="require_link_approval",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="clickevent",
            name="ip_address",
            field=models.GenericIPAddressField(blank=True, db_index=True, null=True),
        ),
        migrations.CreateModel(
            name="ApprovalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], db_index=True, default="PENDING", max_length=12)),
                ("requester_comment", models.TextField(blank=True)),
                ("reviewer_comment", models.TextField(blank=True)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("campaign", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="approval_requests", to="url_short.campaign")),
                ("link", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="approval_requests", to="url_short.urlmodel")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requested_approvals", to=settings.AUTH_USER_MODEL)),
                ("reviewer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_approvals", to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="approval_requests", to="url_short.workspace")),
            ],
            options={"ordering": ("-submitted_at",)},
        ),
        migrations.CreateModel(
            name="AbuseReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reporter_email", models.EmailField(blank=True, max_length=254)),
                ("reason", models.CharField(choices=[("PHISHING", "Phishing"), ("MALWARE", "Malware"), ("SPAM", "Spam"), ("IMPERSONATION", "Impersonation"), ("ILLEGAL_CONTENT", "Illegal content"), ("OTHER", "Other")], max_length=24)),
                ("details", models.TextField(blank=True, max_length=2000)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("UNDER_REVIEW", "Under review"), ("ACTIONED", "Actioned"), ("DISMISSED", "Dismissed")], db_index=True, default="OPEN", max_length=16)),
                ("resolution", models.TextField(blank=True, max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("link", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="abuse_reports", to="url_short.urlmodel")),
                ("reporter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="submitted_abuse_reports", to=settings.AUTH_USER_MODEL)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_abuse_reports", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.CheckConstraint(
                check=models.Q(models.Q(("campaign__isnull", True), ("link__isnull", False)), models.Q(("campaign__isnull", False), ("link__isnull", True)), _connector="OR"),
                name="approval_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.UniqueConstraint(condition=models.Q(("link__isnull", False), ("status", "PENDING")), fields=("link",), name="one_pending_approval_per_link"),
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.UniqueConstraint(condition=models.Q(("campaign__isnull", False), ("status", "PENDING")), fields=("campaign",), name="one_pending_approval_per_campaign"),
        ),
        migrations.AddIndex(
            model_name="abusereport",
            index=models.Index(fields=["status", "-created_at"], name="url_short_a_status_c8ee06_idx"),
        ),
    ]
