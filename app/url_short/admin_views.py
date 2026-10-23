from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    AbuseReport,
    AnalyticsAnomaly,
    ApiCredential,
    ApprovalRequest,
    AuditLog,
    Campaign,
    ClickEvent,
    ConversionEvent,
    CustomDomain,
    NotificationDelivery,
    WebhookDelivery,
    WebhookEndpoint,
    Workspace,
    urlModel,
)
from .permissions import platform_admin_required
from .services import record_audit


@platform_admin_required
def admin_dashboard(request):
    User = get_user_model()
    now = timezone.now()
    today = timezone.localdate()
    week_ago = now - timedelta(days=7)
    traffic_by_owner = (
        urlModel.objects.filter(owner_id=OuterRef("pk"))
        .values("owner_id")
        .annotate(total=Sum("count"))
        .values("total")[:1]
    )
    users = User.objects.annotate(
        workspace_count=Count("workspace_memberships__workspace", distinct=True),
        links_created=Count("short_urls", distinct=True),
        traffic=Coalesce(Subquery(traffic_by_owner, output_field=IntegerField()), 0),
    ).order_by("-date_joined")
    links = urlModel.objects.all()
    clicks = ClickEvent.objects.all()

    context = {
        "total_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "new_users": users.filter(date_joined__gte=week_ago).count(),
        "total_links": links.count(),
        "active_links": links.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now),
            Q(active_from__isnull=True) | Q(active_from__lte=now),
            is_enabled=True,
            approval_status=urlModel.ApprovalStatus.APPROVED,
        ).exclude(safety_status=urlModel.SafetyStatus.MALICIOUS).count(),
        "expired_links": links.filter(expires_at__lte=now).count(),
        "total_clicks": clicks.count(),
        "clicks_today": clicks.filter(clicked_at__date=today).count(),
        "total_workspaces": Workspace.objects.filter(is_active=True).count(),
        "total_campaigns": Campaign.objects.count(),
        "total_conversions": ConversionEvent.objects.count(),
        "human_clicks": clicks.filter(
            bot_classification=ClickEvent.BotClassification.HUMAN
        ).count(),
        "bot_clicks": clicks.filter(
            bot_classification__in=(
                ClickEvent.BotClassification.KNOWN_BOT,
                ClickEvent.BotClassification.LIKELY_BOT,
            )
        ).count(),
        "open_reports": AbuseReport.objects.filter(
            status__in=(AbuseReport.Status.OPEN, AbuseReport.Status.UNDER_REVIEW)
        ).count(),
        "blocked_links": links.filter(
            Q(is_enabled=False) | Q(safety_status=urlModel.SafetyStatus.MALICIOUS)
        ).count(),
        "open_approvals": ApprovalRequest.objects.filter(
            status=ApprovalRequest.Status.PENDING
        ).count(),
        "users": users[:50],
        "recent_audit_logs": AuditLog.objects.select_related("actor", "workspace")[:20],
        "recent_campaigns": Campaign.objects.select_related("workspace", "created_by")[:20],
        "domains": CustomDomain.objects.select_related("workspace")[:20],
        "approval_requests": ApprovalRequest.objects.select_related("workspace", "requester", "link", "campaign")[:20],
        "api_credentials": ApiCredential.objects.select_related("workspace", "created_by")[:20],
        "webhook_endpoints": WebhookEndpoint.objects.select_related("workspace")[:20],
        "webhook_failures": WebhookDelivery.objects.exclude(status=WebhookDelivery.Status.SUCCEEDED).count(),
        "security_findings": AnalyticsAnomaly.objects.select_related("workspace", "link")[:20],
        "notification_failures": NotificationDelivery.objects.filter(status=NotificationDelivery.Status.FAILED).count(),
    }
    return render(request, "admin_dashboard/index.html", context)


@platform_admin_required
def system_health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database_state = "healthy"
        database_detail = f"Connected through Django's {connection.vendor} backend."
    except Exception as exc:
        database_state = "critical"
        database_detail = f"Database check failed: {exc}"

    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    cache_is_external = "redis" in cache_backend.lower()
    email_backend = settings.EMAIL_BACKEND.rsplit(".", 1)[-1]
    email_is_delivery_backend = not any(
        name in settings.EMAIL_BACKEND.lower() for name in ("console", "locmem", "dummy")
    )
    checks = [
        {"name": "Django application", "state": "healthy", "detail": "The application process is responding."},
        {"name": "Database", "state": database_state, "detail": database_detail},
        {
            "name": "Redis cache",
            "state": "healthy" if cache_is_external else "warning",
            "detail": f"Configured backend: {cache_backend.rsplit('.', 1)[-1] or 'none'}.",
        },
        {
            "name": "Kafka event stream",
            "state": "warning",
            "detail": "No Kafka runtime is configured in this deployment.",
        },
        {
            "name": "Background workers",
            "state": "warning",
            "detail": "Jobs use the deployment scheduler; no in-process worker heartbeat is available.",
        },
        {
            "name": "Email delivery",
            "state": "healthy" if email_is_delivery_backend else "warning",
            "detail": f"Configured backend: {email_backend}.",
        },
        {
            "name": "AI provider",
            "state": "healthy" if settings.ORBITLINK_AI_API_KEY else "warning",
            "detail": (
                f"Provider credentials are configured for {settings.ORBITLINK_AI_MODEL}."
                if settings.ORBITLINK_AI_API_KEY
                else "Provider credentials are not configured; deterministic fallbacks remain available."
            ),
        },
        {"name": "Prometheus metrics", "state": "healthy", "detail": "The /metrics endpoint is enabled."},
    ]
    return render(request, "admin_dashboard/system_health.html", {"checks": checks})


@platform_admin_required
@require_POST
def admin_user_status(request, user_id):
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)
    action = request.POST.get("action")
    if target == request.user and action == "disable":
        messages.error(request, "You cannot disable your own administrator account.")
        return redirect("admin_dashboard")
    if action not in {"disable", "reactivate"}:
        messages.error(request, "Unknown user status action.")
        return redirect("admin_dashboard")

    target.is_active = action == "reactivate"
    target.save(update_fields=["is_active"])
    record_audit(
        action="USER_REACTIVATED" if target.is_active else "USER_DISABLED",
        actor=request.user,
        target=target,
        metadata={"username": target.username},
    )
    result_label = "reactivated" if target.is_active else "disabled"
    messages.success(request, f"{target.username} was {result_label}.")
    return redirect("admin_dashboard")


@platform_admin_required
def admin_user_detail(request, user_id):
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)
    return render(
        request,
        "admin_dashboard/user_detail.html",
        {
            "account": target,
            "memberships": target.workspace_memberships.select_related("workspace"),
            "links": target.short_urls.select_related("workspace", "campaign").order_by("-created_at")[:100],
            "activity": AuditLog.objects.filter(actor=target).select_related("workspace")[:100],
            "reports": AbuseReport.objects.filter(link__owner=target).select_related("link", "resolved_by")[:100],
        },
    )
