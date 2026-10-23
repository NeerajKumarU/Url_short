from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def populate_conversion_tokens(apps, schema_editor):
    ClickEvent = apps.get_model("url_short", "ClickEvent")
    for event in ClickEvent.objects.filter(conversion_token__isnull=True).iterator():
        event.conversion_token = uuid.uuid4()
        event.save(update_fields=("conversion_token",))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("url_short", "0005_link_intelligence"),
    ]

    operations = [
        migrations.CreateModel(
            name="Experiment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Draft"), ("ACTIVE", "Active"), ("PAUSED", "Paused"), ("COMPLETED", "Completed")],
                        db_index=True,
                        default="DRAFT",
                        max_length=12,
                    ),
                ),
                (
                    "assignment_strategy",
                    models.CharField(
                        choices=[("DETERMINISTIC", "Stable visitor assignment"), ("RANDOM", "Random per click")],
                        default="DETERMINISTIC",
                        max_length=16,
                    ),
                ),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_experiments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="experiments",
                        to="url_short.urlmodel",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddField(
            model_name="clickevent",
            name="conversion_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_conversion_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="clickevent",
            name="conversion_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="conversion_tracking_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="ExperimentVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("destination_url", models.URLField(max_length=2048)),
                ("weight", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "experiment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variants",
                        to="url_short.experiment",
                    ),
                ),
            ],
            options={"ordering": ("pk",)},
        ),
        migrations.CreateModel(
            name="ConversionEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("SIGNUP", "Signup"),
                            ("PURCHASE", "Purchase"),
                            ("DOWNLOAD", "Download"),
                            ("FORM_SUBMISSION", "Form submission"),
                            ("CUSTOM", "Custom"),
                        ],
                        max_length=24,
                    ),
                ),
                ("custom_name", models.CharField(blank=True, max_length=100)),
                ("monetary_value", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("currency", models.CharField(blank=True, max_length=3)),
                ("deduplication_key", models.CharField(blank=True, max_length=128)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conversions",
                        to="url_short.campaign",
                    ),
                ),
                (
                    "click",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conversions",
                        to="url_short.clickevent",
                    ),
                ),
                (
                    "experiment_variant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conversions",
                        to="url_short.experimentvariant",
                    ),
                ),
                (
                    "link",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conversions",
                        to="url_short.urlmodel",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddField(
            model_name="clickevent",
            name="experiment_variant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="click_events",
                to="url_short.experimentvariant",
            ),
        ),
        migrations.AddConstraint(
            model_name="experimentvariant",
            constraint=models.UniqueConstraint(fields=("experiment", "name"), name="unique_experiment_variant_name"),
        ),
        migrations.AddConstraint(
            model_name="experimentvariant",
            constraint=models.CheckConstraint(
                check=models.Q(("weight__gte", 1), ("weight__lte", 100)),
                name="experiment_variant_weight_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="experiment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")),
                fields=("link",),
                name="one_active_experiment_per_link",
            ),
        ),
        migrations.AddConstraint(
            model_name="experiment",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("start_at__isnull", True),
                    ("end_at__isnull", True),
                    ("end_at__gte", models.F("start_at")),
                    _connector="OR",
                ),
                name="experiment_end_not_before_start",
            ),
        ),
        migrations.AddIndex(
            model_name="conversionevent",
            index=models.Index(fields=["link", "event_type", "-created_at"], name="url_short_c_link_id_57e026_idx"),
        ),
        migrations.AddConstraint(
            model_name="conversionevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deduplication_key", ""), _negated=True),
                fields=("link", "deduplication_key"),
                name="unique_link_conversion_deduplication_key",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversionevent",
            constraint=models.CheckConstraint(
                check=models.Q(("monetary_value__isnull", True), ("monetary_value__gte", 0), _connector="OR"),
                name="conversion_value_nonnegative",
            ),
        ),
    ]
