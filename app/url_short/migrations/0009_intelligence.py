from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("url_short", "0008_integrations")]

    operations = [
        migrations.AddField(
            model_name="clickevent",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="clickevent",
            name="country_code",
            field=models.CharField(blank=True, db_index=True, max_length=2),
        ),
        migrations.AddField(
            model_name="clickevent",
            name="region",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="workspace",
            name="analytics_retention_days",
            field=models.PositiveSmallIntegerField(default=90),
        ),
        migrations.CreateModel(
            name="NotificationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=48)),
                ("recipient", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("SENT", "Sent"), ("FAILED", "Failed")], max_length=8)),
                ("error", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("workspace", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notification_deliveries", to="url_short.workspace")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="AnalyticsAnomaly",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anomaly_type", models.CharField(choices=[("TRAFFIC_SPIKE", "Traffic spike"), ("TRAFFIC_DROP", "Traffic drop"), ("BOT_SPIKE", "Bot spike"), ("REFERRER_SHIFT", "Abnormal referrer distribution"), ("GEO_SHIFT", "Unusual geography"), ("CONVERSION_DROP", "Conversion drop")], db_index=True, max_length=24)),
                ("severity", models.CharField(choices=[("INFO", "Info"), ("WARNING", "Warning"), ("CRITICAL", "Critical")], db_index=True, max_length=12)),
                ("baseline_value", models.FloatField()),
                ("observed_value", models.FloatField()),
                ("explanation", models.CharField(max_length=500)),
                ("detected_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("campaign", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="analytics_anomalies", to="url_short.campaign")),
                ("link", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="analytics_anomalies", to="url_short.urlmodel")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analytics_anomalies", to="url_short.workspace")),
            ],
            options={
                "ordering": ("-detected_at",),
                "indexes": [models.Index(fields=["workspace", "-detected_at"], name="url_short_a_workspa_fa8626_idx")],
            },
        ),
    ]
