import secrets
import string
from datetime import timedelta
from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, F, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .analytics import event_details
from .bot_detection import classify_request_bot
from .conversions import destination_with_conversion_token
from .experiments import select_experiment_variant, set_assignment_cookie
from .forms import LinkEditForm, RegisterForm, ShortUrlForm
from .link_services import create_link_version, public_url_for_link
from .models import ClickEvent, ConversionEvent, RedirectRule, WorkspaceMembership, urlModel
from .permissions import require_link_access, require_workspace_role, workspace_role
from .routing import resolve_destination
from .security import assess_destination
from .selectors import get_current_workspace, links_for_workspace
from .services import ensure_personal_workspace, record_audit
from .webhooks import queue_webhook_event


_metrics = {"requests_total": 0, "shorturls_created_total": 0, "redirects_total": 0}
AUTO_ALIAS_ALPHABET = string.ascii_lowercase + string.digits


def home(request):
    _metrics["requests_total"] += 1
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "index.html")


def product_overview(request):
    """Public product overview, also available to signed-in users."""
    return render(request, "index.html")


@login_required
def create_link_page(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.EDITOR)
    return render(
        request,
        "links/create.html",
        {"form": ShortUrlForm(workspace=workspace), "workspace": workspace},
    )


@login_required
def my_links(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    now = timezone.now()
    links = links_for_workspace(request.user, workspace).select_related("campaign")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    sort = request.GET.get("sort", "newest")

    if query:
        links = links.filter(
            Q(shorturl__icontains=query)
            | Q(longurl__icontains=query)
            | Q(campaign__name__icontains=query)
        )
    if status == "active":
        links = links.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now),
            Q(active_from__isnull=True) | Q(active_from__lte=now),
            is_enabled=True,
            approval_status=urlModel.ApprovalStatus.APPROVED,
        ).exclude(safety_status=urlModel.SafetyStatus.MALICIOUS)
    elif status == "expired":
        links = links.filter(expires_at__lte=now)
    elif status == "disabled":
        links = links.filter(is_enabled=False)
    elif status == "scheduled":
        links = links.filter(active_from__gt=now, is_enabled=True)
    else:
        status = "all"

    order_by = {
        "newest": "-created_at",
        "oldest": "created_at",
        "clicks": "-count",
        "alias": "shorturl",
    }.get(sort, "-created_at")
    if sort not in {"newest", "oldest", "clicks", "alias"}:
        sort = "newest"
    page_obj = Paginator(links.order_by(order_by), 20).get_page(request.GET.get("page"))
    for link in page_obj.object_list:
        link.public_url = public_url_for_link(request, link)
    return render(
        request,
        "links/list.html",
        {
            "workspace": workspace,
            "page_obj": page_obj,
            "query": query,
            "status_filter": status,
            "sort": sort,
        },
    )


@login_required
def qr_library(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    links = links_for_workspace(request.user, workspace).order_by("-created_at")
    for link in links:
        link.public_url = public_url_for_link(request, link)
    return render(request, "links/qr_library.html", {"workspace": workspace, "links": links})


def health(request):
    """Liveness probe target: process is up and able to respond."""
    return JsonResponse({"status": "ok"})


def ready(request):
    """Readiness probe target: process is up AND the database is reachable."""
    try:
        connection.ensure_connection()
    except Exception as exc:
        return JsonResponse({"status": "not ready", "error": str(exc)}, status=503)
    return JsonResponse({"status": "ready"})


def metrics(request):
    """Prometheus scrape target (text exposition format)."""
    body = (
        "# HELP app_requests_total Total HTTP requests received\n"
        "# TYPE app_requests_total counter\n"
        f"app_requests_total {_metrics['requests_total']}\n"
        "# HELP app_shorturls_created_total Total short URLs created\n"
        "# TYPE app_shorturls_created_total counter\n"
        f"app_shorturls_created_total {_metrics['shorturls_created_total']}\n"
        "# HELP app_redirects_total Total successful redirects served\n"
        "# TYPE app_redirects_total counter\n"
        f"app_redirects_total {_metrics['redirects_total']}\n"
    )
    return HttpResponse(body, content_type="text/plain")


def _generate_available_alias(length=6):
    for _ in range(20):
        alias = "".join(secrets.choice(AUTO_ALIAS_ALPHABET) for _ in range(length))
        if not urlModel.objects.filter(shorturl=alias).exists():
            return alias
    raise RuntimeError("Unable to generate a unique short URL. Please try again.")


@login_required
def makeShortUrl(request):
    _metrics["requests_total"] += 1
    if request.method != "POST":
        return redirect("create_link_page")

    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.EDITOR)
    form = ShortUrlForm(request.POST, workspace=workspace)
    if not form.is_valid():
        return render(
            request,
            "links/create.html",
            {"form": form, "workspace": workspace},
            status=400,
        )

    role = workspace_role(request.user, workspace)
    safety = assess_destination(form.cleaned_data["longurl"])
    values = {
        "longurl": form.cleaned_data["longurl"],
        "expires_at": form.cleaned_data["expires_at"],
        "active_from": form.cleaned_data["active_from"],
        "owner": request.user,
        "workspace": workspace,
        "campaign": form.cleaned_data["campaign"],
        "conversion_tracking_enabled": form.cleaned_data["conversion_tracking_enabled"],
        "approval_status": (
            urlModel.ApprovalStatus.DRAFT
            if workspace.require_link_approval and role == WorkspaceMembership.Role.EDITOR
            else urlModel.ApprovalStatus.APPROVED
        ),
        "safety_status": safety.status,
        "safety_detail": safety.detail,
        "safety_checked_at": timezone.now(),
    }
    requested_alias = form.cleaned_data["custom_alias"]
    if requested_alias:
        try:
            with transaction.atomic():
                obj = urlModel.objects.create(shorturl=requested_alias, **values)
        except IntegrityError:
            form.add_error("custom_alias", "This alias is already taken.")
            return render(request, "links/create.html", {"form": form, "workspace": workspace}, status=400)
    else:
        for _ in range(20):
            try:
                with transaction.atomic():
                    obj = urlModel.objects.create(
                        shorturl=_generate_available_alias(),
                        **values,
                    )
                break
            except IntegrityError:
                continue
        else:
            form.add_error(None, "Unable to generate a unique short URL. Please try again.")
            return render(request, "links/create.html", {"form": form, "workspace": workspace}, status=503)

    _metrics["shorturls_created_total"] += 1
    create_link_version(obj, request.user, "Link created")
    record_audit(
        action="LINK_CREATED",
        actor=request.user,
        workspace=workspace,
        target=obj,
        metadata={"alias": obj.shorturl},
    )
    queue_webhook_event(
        workspace,
        "LINK_CREATED",
        {"link_id": obj.pk, "alias": obj.shorturl},
    )
    complete_url = public_url_for_link(request, obj)
    return render(
        request,
        "links/create.html",
        {
            "form": ShortUrlForm(workspace=workspace),
            "created_short_url": complete_url,
            "created_link": obj,
            "workspace": workspace,
        },
    )


def redirecturl(request, shorturl):
    _metrics["requests_total"] += 1
    try:
        obj = urlModel.objects.get(shorturl=shorturl)
    except urlModel.DoesNotExist as exc:
        raise Http404("Short URL not found") from exc

    if obj.security_disabled or (obj.suspended_until and obj.suspended_until > timezone.now()):
        return render(
            request,
            "link_security_suspended.html",
            {"link": obj},
            status=423,
        )
    if obj.is_expired:
        return render(request, "link_expired.html", {"link": obj}, status=410)
    if obj.safety_status == urlModel.SafetyStatus.MALICIOUS:
        return render(request, "link_blocked.html", {"link": obj}, status=451)
    if not obj.is_enabled or (obj.active_from and obj.active_from > timezone.now()):
        return render(
            request,
            "link_unavailable.html",
            {"link": obj, "availability": obj.status_label},
            status=404,
        )
    if obj.approval_status != urlModel.ApprovalStatus.APPROVED:
        return render(
            request,
            "link_unavailable.html",
            {"link": obj, "availability": obj.get_approval_status_display()},
            status=404,
        )

    decision = resolve_destination(obj, request)
    assignment = None
    destination = decision.destination
    if decision.rule is None or decision.rule.condition_type == RedirectRule.ConditionType.DEFAULT:
        assignment = select_experiment_variant(obj, request)
        if assignment:
            destination = assignment.variant.destination_url
    urlModel.objects.filter(pk=obj.pk).update(count=F("count") + 1)
    bot = classify_request_bot(request)
    click = ClickEvent.objects.create(
        short_url=obj,
        routing_rule=decision.rule,
        experiment_variant=assignment.variant if assignment else None,
        resolved_destination=destination,
        bot_classification=bot.classification,
        bot_reason=bot.reason,
        **event_details(request, fingerprint_namespace=f"workspace:{obj.workspace_id or 'legacy'}"),
    )
    _metrics["redirects_total"] += 1
    redirect_destination = (
        destination_with_conversion_token(destination, click.conversion_token)
        if obj.conversion_tracking_enabled
        else destination
    )
    response = redirect(redirect_destination)
    if assignment:
        set_assignment_cookie(response, assignment.new_visitor_id, request)
    return response


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        workspace = ensure_personal_workspace(user)
        record_audit(
            action="USER_REGISTERED",
            actor=user,
            workspace=workspace,
            target=user,
        )
        login(request, user)
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


def _breakdown(queryset, field):
    rows = list(queryset.values(field).annotate(value=Count("id")).order_by("-value"))
    maximum = max((row["value"] for row in rows), default=0)
    return [
        {
            "label": row[field] or "Other",
            "value": row["value"],
            "percent": round((row["value"] / maximum) * 100) if maximum else 0,
        }
        for row in rows
    ]


@login_required
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    links = (
        links_for_workspace(request.user, workspace)
        .annotate(
            last_click=Max("clicks__clicked_at"),
            unique_clickers=Count("clicks__ip_address", distinct=True),
            conversion_count=Count("conversions", distinct=True),
        )
        .order_by("-created_at")
    )
    all_events = ClickEvent.objects.filter(short_url__in=links)
    traffic_filter = request.GET.get("traffic", "all")
    if traffic_filter == "human":
        events = all_events.filter(bot_classification=ClickEvent.BotClassification.HUMAN)
    elif traffic_filter == "bot":
        events = all_events.filter(
            bot_classification__in=(
                ClickEvent.BotClassification.KNOWN_BOT,
                ClickEvent.BotClassification.LIKELY_BOT,
            )
        )
    else:
        traffic_filter = "all"
        events = all_events
    conversions = ConversionEvent.objects.filter(link__in=links)
    total_clicks = links.aggregate(total=Sum("count"))["total"] or 0
    total_conversions = conversions.count()
    current_window_start = now - timedelta(days=7)
    previous_window_start = now - timedelta(days=14)

    def growth(current, previous):
        if previous:
            return round(((current - previous) / previous) * 100, 1)
        return 100.0 if current else 0.0

    current_links = links.filter(created_at__gte=current_window_start).count()
    previous_links = links.filter(
        created_at__gte=previous_window_start,
        created_at__lt=current_window_start,
    ).count()
    current_clicks = all_events.filter(clicked_at__gte=current_window_start).count()
    previous_clicks = all_events.filter(
        clicked_at__gte=previous_window_start,
        clicked_at__lt=current_window_start,
    ).count()
    current_visitors = (
        all_events.filter(clicked_at__gte=current_window_start)
        .exclude(ip_address__isnull=True)
        .values("ip_address")
        .distinct()
        .count()
    )
    previous_visitors = (
        all_events.filter(
            clicked_at__gte=previous_window_start,
            clicked_at__lt=current_window_start,
        )
        .exclude(ip_address__isnull=True)
        .values("ip_address")
        .distinct()
        .count()
    )
    current_conversions = conversions.filter(created_at__gte=current_window_start).count()
    previous_conversions = conversions.filter(
        created_at__gte=previous_window_start,
        created_at__lt=current_window_start,
    ).count()
    human_clicks = all_events.filter(
        bot_classification=ClickEvent.BotClassification.HUMAN
    ).count()
    bot_clicks = all_events.filter(
        bot_classification__in=(
            ClickEvent.BotClassification.KNOWN_BOT,
            ClickEvent.BotClassification.LIKELY_BOT,
        )
    ).count()
    unique_visitors = (
        all_events.exclude(ip_address__isnull=True)
        .exclude(ip_address="")
        .values("ip_address")
        .distinct()
        .count()
    )

    daily_counts = {
        row["day"]: row["value"]
        for row in events.filter(clicked_at__date__gte=week_start)
        .annotate(day=TruncDate("clicked_at"))
        .values("day")
        .annotate(value=Count("id"))
    }
    click_timeline = []
    timeline_max = max(daily_counts.values(), default=0)
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        value = daily_counts.get(day, 0)
        click_timeline.append(
            {
                "label": day.strftime("%a"),
                "date": day,
                "value": value,
                "percent": round((value / timeline_max) * 100) if timeline_max else 0,
            }
        )

    recent_links = list(links[:10])
    for link in recent_links:
        link.public_url = public_url_for_link(request, link)

    context = {
        "base_url": request.build_absolute_uri("/").rstrip("/"),
        "workspace": workspace,
        "workspace_role": request.user.workspace_memberships.filter(
            workspace=workspace, is_active=True
        ).values_list("role", flat=True).first(),
        "workspace_campaigns": workspace.campaigns.count(),
        "active_campaigns": workspace.campaigns.filter(status="ACTIVE").count(),
        "links": recent_links,
        "total_links": links.count(),
        "active_links": links.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).count(),
        "expired_links": links.filter(expires_at__lte=now).count(),
        "total_clicks": total_clicks,
        "filtered_clicks": events.count(),
        "human_clicks": human_clicks,
        "bot_clicks": bot_clicks,
        "unique_visitors": unique_visitors,
        "traffic_filter": traffic_filter,
        "clicks_today": events.filter(clicked_at__date=today).count(),
        "clicks_week": events.filter(clicked_at__date__gte=week_start).count(),
        "total_conversions": total_conversions,
        "conversion_rate": round((total_conversions / total_clicks) * 100, 1) if total_clicks else 0,
        "link_growth": growth(current_links, previous_links),
        "click_growth": growth(current_clicks, previous_clicks),
        "visitor_growth": growth(current_visitors, previous_visitors),
        "conversion_growth": growth(current_conversions, previous_conversions),
        "click_timeline": click_timeline,
        "top_links": links.order_by("-count", "shorturl")[:5],
        "recent_clicks": all_events.select_related("short_url").order_by("-clicked_at")[:6],
        "browser_breakdown": _breakdown(events, "browser"),
        "device_breakdown": _breakdown(events, "device_type"),
        "operating_system_breakdown": _breakdown(events, "operating_system"),
        "referrer_breakdown": _breakdown(events, "referrer_source"),
    }
    return render(request, "dashboard.html", context)


@login_required
def analytics_overview(request):
    """Workspace-scoped traffic intelligence using recorded click and conversion data."""
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    links = links_for_workspace(request.user, workspace)
    events = ClickEvent.objects.filter(short_url__in=links)
    conversions = ConversionEvent.objects.filter(link__in=links)
    today = timezone.localdate()
    range_start = today - timedelta(days=29)
    daily_counts = {
        row["day"]: row["value"]
        for row in events.filter(clicked_at__date__gte=range_start)
        .annotate(day=TruncDate("clicked_at"))
        .values("day")
        .annotate(value=Count("id"))
    }
    maximum = max(daily_counts.values(), default=0)
    timeline = []
    for offset in range(30):
        day = range_start + timedelta(days=offset)
        value = daily_counts.get(day, 0)
        timeline.append({
            "date": day,
            "value": value,
            "percent": round((value / maximum) * 100) if maximum else 0,
        })
    total_clicks = events.count()
    unique_visitors = (
        events.exclude(ip_address__isnull=True)
        .exclude(ip_address="")
        .values("ip_address")
        .distinct()
        .count()
    )
    total_conversions = conversions.count()
    context = {
        "workspace": workspace,
        "total_links": links.count(),
        "total_clicks": total_clicks,
        "unique_visitors": unique_visitors,
        "total_conversions": total_conversions,
        "conversion_rate": round((total_conversions / total_clicks) * 100, 1) if total_clicks else 0,
        "timeline": timeline,
        "browser_breakdown": _breakdown(events, "browser")[:6],
        "device_breakdown": _breakdown(events, "device_type")[:6],
        "operating_system_breakdown": _breakdown(events, "operating_system")[:6],
        "referrer_breakdown": _breakdown(events, "referrer_source")[:6],
        "top_links": links.annotate(event_count=Count("clicks")).order_by("-event_count", "shorturl")[:6],
    }
    return render(request, "analytics/overview.html", context)


@login_required
def audience_overview(request):
    """Workspace-scoped geographic and technology audience intelligence."""
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    links = links_for_workspace(request.user, workspace)
    events = ClickEvent.objects.filter(short_url__in=links)
    human_events = events.filter(bot_classification=ClickEvent.BotClassification.HUMAN)
    known_visitors = events.exclude(ip_address__isnull=True).exclude(ip_address="")
    unique_visitors = known_visitors.values("ip_address").distinct().count()
    returning_visitors = (
        known_visitors.values("ip_address")
        .annotate(visits=Count("id"))
        .filter(visits__gt=1)
        .count()
    )
    countries = _breakdown(events.exclude(country_code=""), "country_code")[:10]
    context = {
        "workspace": workspace,
        "total_events": events.count(),
        "human_events": human_events.count(),
        "unique_visitors": unique_visitors,
        "returning_visitors": returning_visitors,
        "returning_rate": round((returning_visitors / unique_visitors) * 100, 1) if unique_visitors else 0,
        "country_breakdown": countries,
        "region_breakdown": _breakdown(events.exclude(region=""), "region")[:8],
        "city_breakdown": _breakdown(events.exclude(city=""), "city")[:8],
        "device_breakdown": _breakdown(events, "device_type")[:6],
        "browser_breakdown": _breakdown(events, "browser")[:6],
        "globe_country_codes": [item["label"] for item in countries],
    }
    return render(request, "analytics/audience.html", context)


@login_required
def edit_short_url(request, pk):
    link = get_object_or_404(urlModel.objects.select_related("workspace"), pk=pk)
    require_link_access(request.user, link, WorkspaceMembership.Role.EDITOR)
    form = LinkEditForm(request.POST or None, instance=link, workspace=link.workspace)
    if request.method == "POST" and form.is_valid():
        old_destination = link.longurl
        form.save()
        if old_destination != link.longurl:
            safety = assess_destination(link.longurl)
            link.safety_status = safety.status
            link.safety_detail = safety.detail
            link.safety_checked_at = timezone.now()
            if (
                link.workspace
                and link.workspace.require_link_approval
                and workspace_role(request.user, link.workspace) == WorkspaceMembership.Role.EDITOR
            ):
                link.approval_status = urlModel.ApprovalStatus.DRAFT
            link.save(
                update_fields=(
                    "safety_status",
                    "safety_detail",
                    "safety_checked_at",
                    "approval_status",
                    "updated_at",
                )
            )
        create_link_version(link, request.user, "Link settings updated")
        record_audit(
            action="LINK_UPDATED",
            actor=request.user,
            workspace=link.workspace,
            target=link,
            metadata={
                "alias": link.shorturl,
                "destination_changed": old_destination != link.longurl,
            },
        )
        if link.workspace_id:
            queue_webhook_event(
                link.workspace,
                "LINK_UPDATED",
                {"link_id": link.pk, "alias": link.shorturl},
            )
        messages.success(request, f"/{link.shorturl} was updated.")
        return redirect("dashboard")
    return render(request, "link_edit.html", {"form": form, "link": link})


@login_required
def qr_code(request, pk):
    link = get_object_or_404(urlModel.objects.select_related("workspace"), pk=pk)
    require_link_access(request.user, link, WorkspaceMembership.Role.VIEWER)
    short_url = public_url_for_link(request, link)
    image = qrcode.make(short_url)
    output = BytesIO()
    image.save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    disposition = "attachment" if request.GET.get("download") == "1" else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{link.shorturl}-qr.png"'
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
@require_POST
def delete_short_url(request, pk):
    link = get_object_or_404(urlModel.objects.select_related("workspace"), pk=pk)
    require_link_access(request.user, link, WorkspaceMembership.Role.EDITOR)
    alias = link.shorturl
    workspace = link.workspace
    link_id = link.pk
    link.delete()
    record_audit(
        action="LINK_DELETED",
        actor=request.user,
        workspace=workspace,
        metadata={"alias": alias, "deleted_link_id": link_id},
    )
    messages.success(request, f"/{alias} was deleted.")
    return redirect("dashboard")
