from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def create_personal_workspaces(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Workspace = apps.get_model("url_short", "Workspace")
    Membership = apps.get_model("url_short", "WorkspaceMembership")
    UrlModel = apps.get_model("url_short", "urlModel")

    for user in User.objects.order_by("pk").iterator():
        base = (slugify(user.username) or f"user-{user.pk}")[:125]
        base = f"{base}-workspace"
        slug = base
        suffix = 2
        while Workspace.objects.filter(slug=slug).exists():
            suffix_text = f"-{suffix}"
            slug = f"{base[:140 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        workspace = Workspace.objects.create(
            name=f"{user.username}'s workspace",
            slug=slug,
            owner_id=user.pk,
        )
        Membership.objects.create(
            workspace_id=workspace.pk,
            user_id=user.pk,
            role="OWNER",
            is_active=True,
        )
        UrlModel.objects.filter(owner_id=user.pk, workspace_id__isnull=True).update(
            workspace_id=workspace.pk
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("url_short", "0003_link_expiry_and_click_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="Workspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="owned_workspaces",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("name", "pk")},
        ),
        migrations.CreateModel(
            name="WorkspaceMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[("OWNER", "Owner"), ("ADMIN", "Admin"), ("EDITOR", "Editor"), ("VIEWER", "Viewer")],
                        default="VIEWER",
                        max_length=12,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="url_short.workspace",
                    ),
                ),
            ],
            options={"ordering": ("workspace__name", "user__username")},
        ),
        migrations.AddField(
            model_name="workspace",
            name="members",
            field=models.ManyToManyField(
                related_name="workspaces",
                through="url_short.WorkspaceMembership",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="Campaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Draft"), ("ACTIVE", "Active"), ("PAUSED", "Paused"), ("ENDED", "Ended")],
                        db_index=True,
                        default="DRAFT",
                        max_length=12,
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
                        related_name="created_campaigns",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="campaigns",
                        to="url_short.workspace",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(db_index=True, max_length=64)),
                ("target_type", models.CharField(blank=True, max_length=64)),
                ("target_id", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="url_short.workspace",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="campaign",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="links",
                to="url_short.campaign",
            ),
        ),
        migrations.AddField(
            model_name="urlmodel",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="links",
                to="url_short.workspace",
            ),
        ),
        migrations.RunPython(create_personal_workspaces, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="urlmodel",
            index=models.Index(fields=["workspace", "-created_at"], name="url_short_u_workspa_ad9b7b_idx"),
        ),
        migrations.AddIndex(
            model_name="urlmodel",
            index=models.Index(fields=["campaign", "-created_at"], name="url_short_u_campaig_96b039_idx"),
        ),
        migrations.AddIndex(
            model_name="workspacemembership",
            index=models.Index(fields=["user", "is_active", "role"], name="url_short_w_user_id_db31f4_idx"),
        ),
        migrations.AddConstraint(
            model_name="workspacemembership",
            constraint=models.UniqueConstraint(fields=("workspace", "user"), name="unique_workspace_membership"),
        ),
        migrations.AddIndex(
            model_name="campaign",
            index=models.Index(fields=["workspace", "status", "-created_at"], name="url_short_c_workspa_4cdcf3_idx"),
        ),
        migrations.AddConstraint(
            model_name="campaign",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("start_at__isnull", True),
                    ("end_at__isnull", True),
                    ("end_at__gte", models.F("start_at")),
                    _connector="OR",
                ),
                name="campaign_end_not_before_start",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["workspace", "-created_at"], name="url_short_a_workspa_ad6ba3_idx"),
        ),
    ]
