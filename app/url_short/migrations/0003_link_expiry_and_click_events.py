from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("url_short", "0002_custom_alias_and_ownership"),
    ]

    operations = [
        migrations.AddField(
            model_name="urlmodel",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ClickEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("clicked_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("referrer", models.CharField(blank=True, max_length=2048)),
                ("browser", models.CharField(default="Other", max_length=32)),
                ("device_type", models.CharField(default="Other", max_length=32)),
                ("operating_system", models.CharField(default="Other", max_length=32)),
                ("referrer_source", models.CharField(default="Direct", max_length=32)),
                (
                    "short_url",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clicks",
                        to="url_short.urlmodel",
                    ),
                ),
            ],
            options={"ordering": ["-clicked_at"]},
        ),
    ]
