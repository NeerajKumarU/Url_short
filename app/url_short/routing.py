from dataclasses import dataclass
from urllib.parse import urlparse

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .analytics import event_details
from .models import RedirectRule


@dataclass(frozen=True)
class RoutingDecision:
    destination: str
    rule: RedirectRule | None = None


def _request_signals(request):
    analytics = event_details(request)
    language = request.META.get("HTTP_ACCEPT_LANGUAGE", "").split(",", 1)[0]
    language = language.split(";", 1)[0].strip().lower()
    return {
        **analytics,
        "country": request.META.get("HTTP_CF_IPCOUNTRY", "").upper(),
        "language": language,
    }


def _matches(rule, signals, now):
    expected = rule.match_value.strip()
    expected_lower = expected.lower()
    condition = rule.condition_type
    if condition == RedirectRule.ConditionType.DEFAULT:
        return True
    if condition == RedirectRule.ConditionType.COUNTRY:
        countries = {item.strip().upper() for item in expected.split(",") if item.strip()}
        return signals["country"] in countries
    if condition == RedirectRule.ConditionType.DEVICE:
        return signals["device_type"].lower() == expected_lower
    if condition == RedirectRule.ConditionType.OPERATING_SYSTEM:
        return signals["operating_system"].lower() == expected_lower
    if condition == RedirectRule.ConditionType.BROWSER:
        return signals["browser"].lower() == expected_lower
    if condition == RedirectRule.ConditionType.LANGUAGE:
        return signals["language"].startswith(expected_lower)
    if condition == RedirectRule.ConditionType.REFERRER:
        hostname = (urlparse(signals["referrer"]).hostname or "").lower()
        return expected_lower in hostname
    if condition == RedirectRule.ConditionType.DATE_TIME:
        start_text, separator, end_text = expected.partition("/")
        if not separator:
            return False
        start = parse_datetime(start_text) if start_text else None
        end = parse_datetime(end_text) if end_text else None
        if start and timezone.is_naive(start):
            start = timezone.make_aware(start)
        if end and timezone.is_naive(end):
            end = timezone.make_aware(end)
        return (start is None or now >= start) and (end is None or now <= end)
    return False


def resolve_destination(link, request, *, now=None):
    """Resolve lightweight request rules; unknown signals naturally fall back."""
    now = now or timezone.now()
    signals = _request_signals(request)
    fallback = None
    rules = link.routing_rules.filter(is_active=True).order_by("priority", "pk")
    for rule in rules:
        if rule.condition_type == RedirectRule.ConditionType.DEFAULT:
            fallback = fallback or rule
            continue
        if _matches(rule, signals, now):
            return RoutingDecision(rule.destination_url, rule)
    if fallback:
        return RoutingDecision(fallback.destination_url, fallback)
    return RoutingDecision(link.longurl)


def routing_event_details(request):
    return event_details(request)
