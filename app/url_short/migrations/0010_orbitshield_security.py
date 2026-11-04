from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("url_short", "0009_intelligence"),
    ]

    operations = [
        migrations.AddField(
            model_name="urlmodel",
            name="security_disabled",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="suspended_until",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="suspension_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="clickevent",
            name="ip_fingerprint",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.CreateModel(
            name="WorkspaceSecuritySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monitoring_enabled", models.BooleanField(default=True)),
                ("sensitivity", models.CharField(choices=[("RELAXED", "Relaxed"), ("BALANCED", "Balanced"), ("HIGH", "High sensitivity")], default="BALANCED", max_length=12)),
                ("alert_threshold", models.PositiveSmallIntegerField(default=60)),
                ("email_alerts", models.BooleanField(default=True)),
                ("webhook_alerts", models.BooleanField(default=True)),
                ("automatic_throttling", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workspace", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="security_settings", to="url_short.workspace")),
            ],
        ),
        migrations.CreateModel(
            name="SecurityIncident",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("threat_type", models.CharField(choices=[("TRAFFIC_SPIKE", "Traffic spike"), ("REPEATED_IP", "Repeated visitor activity"), ("BOT_ACTIVITY", "Automated bot activity"), ("GEO_ANOMALY", "Geographic anomaly"), ("USER_AGENT_ANOMALY", "User-agent anomaly"), ("CLICK_VELOCITY", "Abnormal click velocity"), ("COMPOSITE", "Multiple threat signals")], db_index=True, max_length=32)),
                ("severity", models.CharField(choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("CRITICAL", "Critical")], db_index=True, max_length=12)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("INVESTIGATING", "Investigating"), ("RESOLVED", "Resolved"), ("DISMISSED", "False positive")], db_index=True, default="OPEN", max_length=16)),
                ("risk_score", models.PositiveSmallIntegerField(db_index=True)),
                ("signals", models.JSONField(default=list)),
                ("explanation", models.CharField(max_length=1000)),
                ("observed_clicks", models.PositiveIntegerField(default=0)),
                ("baseline_clicks", models.FloatField(default=0)),
                ("first_detected_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_detected_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("resolution_note", models.TextField(blank=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("investigated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="investigated_security_incidents", to=settings.AUTH_USER_MODEL)),
                ("link", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="security_incidents", to="url_short.urlmodel")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="security_incidents", to="url_short.workspace")),
            ],
            options={
                "ordering": ("-risk_score", "-last_detected_at"),
                "indexes": [
                    models.Index(fields=["workspace", "status", "-last_detected_at"], name="sec_inc_ws_status_idx"),
                    models.Index(fields=["workspace", "severity", "-last_detected_at"], name="sec_inc_ws_sev_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="workspacesecuritysettings",
            constraint=models.CheckConstraint(check=models.Q(("alert_threshold__gte", 20), ("alert_threshold__lte", 100)), name="security_alert_threshold_20_100"),
        ),
        migrations.AddConstraint(
            model_name="securityincident",
            constraint=models.CheckConstraint(check=models.Q(("risk_score__gte", 0), ("risk_score__lte", 100)), name="security_incident_score_0_100"),
        ),
        migrations.AddConstraint(
            model_name="securityincident",
            constraint=models.UniqueConstraint(condition=models.Q(("link__isnull", False), ("status__in", ("OPEN", "INVESTIGATING"))), fields=("workspace", "link"), name="one_active_security_incident_per_link"),
        ),
    ]
