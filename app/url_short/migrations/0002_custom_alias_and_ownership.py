from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def make_shorturls_unique(apps, schema_editor):
    UrlModel = apps.get_model("url_short", "urlModel")
    seen = set()
    for link in UrlModel.objects.order_by("pk").iterator():
        if link.shorturl not in seen:
            seen.add(link.shorturl)
            continue

        base = link.shorturl[:35]
        candidate = f"{base}-{link.pk}"
        suffix = 1
        while candidate in seen or UrlModel.objects.filter(shorturl=candidate).exists():
            candidate = f"{base}-{link.pk}-{suffix}"
            suffix += 1
        link.shorturl = candidate
        link.save(update_fields=["shorturl"])
        seen.add(candidate)


class Migration(migrations.Migration):
    dependencies = [
        ("url_short", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="urlmodel",
            name="shorturl",
            field=models.CharField(max_length=50),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="short_urls",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(make_shorturls_unique, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="urlmodel",
            name="shorturl",
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
