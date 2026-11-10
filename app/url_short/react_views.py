"""Read-only React migration adapter.

The adapter exposes authorized view models for the parallel React shell while all
existing Django routes and mutation contracts remain unchanged.
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone

from .context_processors import application_shell
from .link_services import public_url_for_link
from .models import ClickEvent, ConversionEvent, WorkspaceMembership, urlModel
from .permissions import require_workspace_role
from .selectors import campaigns_for_workspace, get_current_workspace, links_for_workspace
from .security_views import build_security_payload


def _breakdown(queryset, field, limit=None):
    rows = list(queryset.values(field).annotate(value=Count("id")).order_by("-value"))
    if limit:
        rows = rows[:limit]
    maximum = max((row["value"] for row in rows), default=0)
    return [
        {
            "label": row[field] or "Other",
            "value": row["value"],
            "percent": round((row["value"] / maximum) * 100) if maximum else 0,
        }
        for row in rows
    ]


def _growth(current, previous):
    if previous:
        return round(((current - previous) / previous) * 100, 1)
    return 100.0 if current else 0.0


def _membership(request, workspace):
    return request.user.workspace_memberships.filter(
        workspace=workspace,
        is_active=True,
    ).first()


def _shell_payload(request, workspace):
    context = application_shell(request)
    membership = context.get("shell_membership") or _membership(request, workspace)
    role_label = membership.get_role_display() if membership else "Platform administrator"
    return {
        "user": {
            "id": request.user.pk,
            "username": request.user.username,
            "email": request.user.email,
        },
        "workspace": {"id": workspace.pk, "name": workspace.name, "slug": workspace.slug},
        "membership": {"role": membership.role if membership else "OWNER", "role_label": role_label},
        "permissions": {
            "can_edit": bool(context.get("shell_can_edit")),
            "can_admin": bool(context.get("shell_can_admin")),
            "is_platform_admin": bool(context.get("shell_is_platform_admin")),
        },
        "anomaly_count": context.get("shell_anomaly_count", 0),
        "approval_count": context.get("shell_approval_count", 0),
        "notification_count": context.get("shell_notification_count", 0),
        "security_count": context.get("shell_security_count", 0),
        "csrf_token": get_token(request),
    }


def _link_payload(request, link):
    return {
        "id": link.pk,
        "alias": link.shorturl,
        "destination": link.longurl,
        "public_url": public_url_for_link(request, link),
        "campaign": link.campaign.name if link.campaign_id else None,
        "status": link.status_label,
        "clicks": link.count,
        "created_at": link.created_at,
        "expires_at": link.expires_at,
    }


def _dashboard_payload(request, workspace, links):
    now = timezone.now()
    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    current_start = now - timedelta(days=7)
    previous_start = now - timedelta(days=14)
    annotated_links = links.annotate(conversion_count=Count("conversions", distinct=True))
    events = ClickEvent.objects.filter(short_url__in=links)
    conversions = ConversionEvent.objects.filter(link__in=links)
    total_clicks = links.aggregate(total=Sum("count"))["total"] or 0
    unique_visitors = events.exclude(ip_address__isnull=True).exclude(ip_address="").values("ip_address").distinct().count()
    current_visitors = events.filter(clicked_at__gte=current_start).exclude(ip_address__isnull=True).values("ip_address").distinct().count()
    previous_visitors = events.filter(clicked_at__gte=previous_start, clicked_at__lt=current_start).exclude(ip_address__isnull=True).values("ip_address").distinct().count()
    daily = {
        row["day"]: row["value"]
        for row in events.filter(clicked_at__date__gte=week_start)
        .annotate(day=TruncDate("clicked_at"))
        .values("day")
        .annotate(value=Count("id"))
    }
    timeline = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        timeline.append({"date": day.isoformat(), "label": day.strftime("%a"), "value": daily.get(day, 0)})
    top_links = []
    for link in annotated_links.order_by("-count", "shorturl")[:5]:
        top_links.append({
            "id": link.pk,
            "alias": link.shorturl,
            "clicks": link.count,
            "conversions": link.conversion_count,
            "share": round((link.count / total_clicks) * 100) if total_clicks else 0,
        })
    recent_clicks = [
        {
            "id": click.pk,
            "link_id": click.short_url_id,
            "alias": click.short_url.shorturl,
            "browser": click.browser,
            "device": click.device_type,
            "country": click.country_code,
            "clicked_at": click.clicked_at,
        }
        for click in events.select_related("short_url").order_by("-clicked_at")[:6]
    ]
    current_links = links.filter(created_at__gte=current_start).count()
    previous_links = links.filter(created_at__gte=previous_start, created_at__lt=current_start).count()
    current_clicks = events.filter(clicked_at__gte=current_start).count()
    previous_clicks = events.filter(clicked_at__gte=previous_start, clicked_at__lt=current_start).count()
    current_conversions = conversions.filter(created_at__gte=current_start).count()
    previous_conversions = conversions.filter(created_at__gte=previous_start, created_at__lt=current_start).count()
    return {
        "workspace_name": workspace.name,
        "total_links": links.count(),
        "total_clicks": total_clicks,
        "unique_visitors": unique_visitors,
        "total_conversions": conversions.count(),
        "growth": {
            "links": _growth(current_links, previous_links),
            "clicks": _growth(current_clicks, previous_clicks),
            "visitors": _growth(current_visitors, previous_visitors),
            "conversions": _growth(current_conversions, previous_conversions),
        },
        "timeline": timeline,
        "top_links": top_links,
        "recent_clicks": recent_clicks,
    }


def _links_payload(request, workspace, links):
    now = timezone.now()
    queryset = links.select_related("campaign")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    sort = request.GET.get("sort", "newest")
    if query:
        queryset = queryset.filter(Q(shorturl__icontains=query) | Q(longurl__icontains=query) | Q(campaign__name__icontains=query))
    if status == "active":
        queryset = queryset.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now), Q(active_from__isnull=True) | Q(active_from__lte=now), is_enabled=True, approval_status=urlModel.ApprovalStatus.APPROVED).exclude(safety_status=urlModel.SafetyStatus.MALICIOUS)
    elif status == "expired":
        queryset = queryset.filter(expires_at__lte=now)
    elif status == "disabled":
        queryset = queryset.filter(is_enabled=False)
    elif status == "scheduled":
        queryset = queryset.filter(active_from__gt=now, is_enabled=True)
    order = {"newest": "-created_at", "oldest": "created_at", "clicks": "-count", "alias": "shorturl"}.get(sort, "-created_at")
    paginator = Paginator(queryset.order_by(order), 20)
    page = paginator.get_page(request.GET.get("page"))
    return {
        "workspace_name": workspace.name,
        "links": [_link_payload(request, link) for link in page.object_list],
        "total": paginator.count,
        "page": page.number,
        "pages": paginator.num_pages,
    }


def _analytics_payload(workspace, links):
    events = ClickEvent.objects.filter(short_url__in=links)
    conversions = ConversionEvent.objects.filter(link__in=links)
    today = timezone.localdate()
    start = today - timedelta(days=29)
    daily = {
        row["day"]: row["value"]
        for row in events.filter(clicked_at__date__gte=start).annotate(day=TruncDate("clicked_at")).values("day").annotate(value=Count("id"))
    }
    maximum = max(daily.values(), default=0)
    timeline = []
    for offset in range(30):
        day = start + timedelta(days=offset)
        value = daily.get(day, 0)
        timeline.append({"date": day.isoformat(), "value": value, "percent": round((value / maximum) * 100) if maximum else 0})
    total_clicks = events.count()
    total_conversions = conversions.count()
    top_links = [
        {"id": link.pk, "alias": link.shorturl, "destination": link.longurl, "events": link.event_count}
        for link in links.annotate(event_count=Count("clicks")).order_by("-event_count", "shorturl")[:6]
    ]
    return {
        "workspace_name": workspace.name,
        "total_links": links.count(),
        "total_clicks": total_clicks,
        "unique_visitors": events.exclude(ip_address__isnull=True).exclude(ip_address="").values("ip_address").distinct().count(),
        "total_conversions": total_conversions,
        "conversion_rate": round((total_conversions / total_clicks) * 100, 1) if total_clicks else 0,
        "timeline": timeline,
        "top_links": top_links,
        "breakdowns": {
            "referrers": _breakdown(events, "referrer_source", 6),
            "devices": _breakdown(events, "device_type", 6),
            "browsers": _breakdown(events, "browser", 6),
            "operating_systems": _breakdown(events, "operating_system", 6),
        },
    }


def _audience_payload(workspace, links):
    events = ClickEvent.objects.filter(short_url__in=links)
    known = events.exclude(ip_address__isnull=True).exclude(ip_address="")
    unique = known.values("ip_address").distinct().count()
    returning = known.values("ip_address").annotate(visits=Count("id")).filter(visits__gt=1).count()
    return {
        "workspace_name": workspace.name,
        "total_events": events.count(),
        "human_events": events.filter(bot_classification=ClickEvent.BotClassification.HUMAN).count(),
        "unique_visitors": unique,
        "returning_visitors": returning,
        "returning_rate": round((returning / unique) * 100, 1) if unique else 0,
        "countries": _breakdown(events.exclude(country_code=""), "country_code", 10),
        "regions": _breakdown(events.exclude(region=""), "region", 8),
        "cities": _breakdown(events.exclude(city=""), "city", 8),
        "devices": _breakdown(events, "device_type", 6),
        "browsers": _breakdown(events, "browser", 6),
    }


def _campaigns_payload(workspace):
    campaigns = campaigns_for_workspace(workspace).annotate(
        link_count=Count("links", distinct=True),
        click_count=Coalesce(Sum("links__count"), 0),
        conversion_count=Count("conversions", distinct=True),
    )
    return {
        "workspace_name": workspace.name,
        "campaigns": [
            {
                "id": campaign.pk,
                "name": campaign.name,
                "description": campaign.description,
                "status": campaign.status,
                "status_label": campaign.get_status_display(),
                "links": campaign.link_count,
                "clicks": campaign.click_count,
                "conversions": campaign.conversion_count,
                "start_at": campaign.start_at,
                "end_at": campaign.end_at,
            }
            for campaign in campaigns
        ],
    }


@login_required
def react_shell(request, path=""):
    return render(request, "react/index.html")


@login_required
def react_bootstrap(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    links = links_for_workspace(request.user, workspace)
    page_name = request.GET.get("_view", "shell")
    builders = {
        "dashboard": lambda: _dashboard_payload(request, workspace, links),
        "links": lambda: _links_payload(request, workspace, links),
        "analytics": lambda: _analytics_payload(workspace, links),
        "audience": lambda: _audience_payload(workspace, links),
        "campaigns": lambda: _campaigns_payload(workspace),
        "qr-codes": lambda: {"workspace_name": workspace.name, "links": [_link_payload(request, link) for link in links.select_related("campaign").order_by("-created_at")]},
        "settings": lambda: {
            "user": {"username": request.user.username, "email": request.user.email, "is_platform_admin": request.user.is_staff or request.user.is_superuser},
            "workspace": {
                "name": workspace.name,
                "role_label": _membership(request, workspace).get_role_display() if _membership(request, workspace) else "Owner",
                "retention_days": workspace.analytics_retention_days,
                "requires_approval": workspace.require_link_approval,
            },
            "can_admin": application_shell(request).get("shell_can_admin", False),
        },
        "security": lambda: build_security_payload(request, workspace),
        "shell": lambda: {},
    }
    if page_name not in builders:
        return JsonResponse({"error": "Unknown React view."}, status=404)
    return JsonResponse({"shell": _shell_payload(request, workspace), "page": builders[page_name]()})
