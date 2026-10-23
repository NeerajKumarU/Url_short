from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .anomalies import detect_workspace_anomalies
from .models import ClickEvent, ConversionEvent, WorkspaceMembership
from .permissions import require_workspace_role
from .selectors import get_current_workspace
from .services import record_audit


@login_required
@require_GET
def realtime_analytics(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    now = timezone.now()
    events = ClickEvent.objects.filter(short_url__workspace=workspace)
    recent = events.filter(clicked_at__gte=now - timedelta(minutes=5))
    today = timezone.localdate()
    bot_values = (
        ClickEvent.BotClassification.KNOWN_BOT,
        ClickEvent.BotClassification.LIKELY_BOT,
    )
    top_links = list(
        workspace.links.annotate(recent_clicks=Count("clicks", filter=Q(clicks__clicked_at__gte=now - timedelta(hours=24))))
        .order_by("-recent_clicks", "shorturl")
        .values("shorturl", "recent_clicks")[:5]
    )
    return JsonResponse(
        {
            "generated_at": now.isoformat(),
            "clicks_last_5_minutes": recent.count(),
            "clicks_today": events.filter(clicked_at__date=today).count(),
            "human_clicks_today": events.filter(clicked_at__date=today, bot_classification=ClickEvent.BotClassification.HUMAN).count(),
            "bot_clicks_today": events.filter(clicked_at__date=today, bot_classification__in=bot_values).count(),
            "conversions_today": ConversionEvent.objects.filter(link__workspace=workspace, created_at__date=today).count(),
            "active_campaigns": workspace.campaigns.filter(status="ACTIVE").count(),
            "top_links_24h": top_links,
        }
    )


@login_required
def anomaly_list(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    anomalies = workspace.analytics_anomalies.select_related("link", "campaign")[:100]
    return render(request, "analytics/anomalies.html", {"workspace": workspace, "anomalies": anomalies})


@login_required
@require_POST
def anomaly_scan(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    created = detect_workspace_anomalies(workspace)
    record_audit(action="ANOMALY_SCAN_RUN", actor=request.user, workspace=workspace, target=workspace, metadata={"created": len(created)})
    messages.success(request, f"Anomaly scan complete. {len(created)} new finding(s).")
    return redirect("anomaly_list")
