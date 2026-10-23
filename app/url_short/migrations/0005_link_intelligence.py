from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import url_short.models


def create_initial_versions(apps, schema_editor):
    UrlModel = apps.get_model("url_short", "urlModel")
    LinkVersion = apps.get_model("url_short", "LinkVersion")
    versions = []
    for link in UrlModel.objects.order_by("pk").iterator():
        versions.append(
            LinkVersion(
                link_id=link.pk,
                version_number=1,
                changed_by_id=link.owner_id,
                change_summary="Initial version created during SaaS migration",
                snapshot={
                    "longurl": link.longurl,
                    "campaign_id": link.campaign_id,
                    "active_from": link.active_from.isoformat() if link.active_from else None,
                    "expires_at": link.expires_at.isoformat() if link.expires_at else None,
                    "is_enabled": link.is_enabled,
                    "utm_parameters": link.utm_parameters or {},
                    "routing_rules": [],
                },
            )
        )
    LinkVersion.objects.bulk_create(versions, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("url_short", "0004_saas_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="clickevent",
            name="resolved_destination",
            field=models.URLField(blank=True, max_length=2048),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="active_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="is_enabled",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="utm_parameters",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="RedirectRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                (
                    "condition_type",
                    models.CharField(
                        choices=[
                            ("COUNTRY", "Country"),
                            ("DEVICE", "Device"),
                            ("OPERATING_SYSTEM", "Operating system"),
                            ("BROWSER", "Browser"),
                            ("LANGUAGE", "Language"),
                            ("DATE_TIME", "Date/time window"),
                            ("REFERRER", "Referrer"),
                            ("DEFAULT", "Default fallback"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "match_value",
                    models.CharField(
                        blank=True,
                        help_text="Value to match. Date/time windows use start/end ISO-8601 values.",
                        max_length=500,
                    ),
                ),
                ("destination_url", models.URLField(max_length=2048)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="routing_rules",
                        to="url_short.urlmodel",
                    ),
                ),
            ],
            options={"ordering": ("priority", "pk")},
        ),
        migrations.CreateModel(
            name="LinkVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_number", models.PositiveIntegerField()),
                ("snapshot", models.JSONField(default=dict)),
                ("change_summary", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="link_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="url_short.urlmodel",
                    ),
                ),
            ],
            options={"ordering": ("-version_number",)},
        ),
        migrations.CreateModel(
            name="CustomDomain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(max_length=253, unique=True)),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("VERIFIED", "Verified"),
                            ("FAILED", "Failed"),
                            ("DISABLED", "Disabled"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                (
                    "verification_token",
                    models.CharField(
                        default=url_short.models.generate_verification_token,
                        editable=False,
                        max_length=128,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_domains",
                        to="url_short.workspace",
                    ),
                ),
            ],
            options={"ordering": ("domain",)},
        ),
        migrations.AddField(
            model_name="clickevent",
            name="routing_rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="clicks",
                to="url_short.redirectrule",
            ),
        ),
        migrations.RunPython(create_initial_versions, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="redirectrule",
            index=models.Index(fields=["link", "is_active", "priority"], name="url_short_r_link_id_070789_idx"),
        ),
        migrations.AddConstraint(
            model_name="linkversion",
            constraint=models.UniqueConstraint(fields=("link", "version_number"), name="unique_link_version_number"),
        ),
        migrations.AddConstraint(
            model_name="customdomain",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("workspace",),
                name="one_default_domain_per_workspace",
            ),
        ),
    ]
