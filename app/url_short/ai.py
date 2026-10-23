import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import AbuseReport, ClickEvent, ConversionEvent, urlModel


@dataclass(frozen=True)
class AIResult:
    available: bool
    text: str = ""
    error: str = ""


class UnavailableAIProvider:
    available = False

    def complete(self, *, system_prompt, user_prompt, context):
        return AIResult(False, error="AI is unavailable because no provider API key is configured.")


class OpenAICompatibleProvider:
    available = True

    def __init__(self, api_key, endpoint, model):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model

    def complete(self, *, system_prompt, user_prompt, context):
        body = json.dumps(
            {
                "model": self.model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Question: {user_prompt}\nAuthorized structured data:\n{json.dumps(context, default=str)}",
                    },
                ],
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return AIResult(True, error=f"The AI provider request failed: {exc}")
        text = payload.get("output_text", "")
        if not text:
            pieces = []
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        pieces.append(content.get("text", ""))
            text = "\n".join(filter(None, pieces))
        return AIResult(True, text=text, error="" if text else "The AI provider returned no text.")


def get_ai_provider():
    api_key = settings.ORBITLINK_AI_API_KEY
    if not api_key:
        return UnavailableAIProvider()
    return OpenAICompatibleProvider(
        api_key,
        settings.ORBITLINK_AI_ENDPOINT,
        settings.ORBITLINK_AI_MODEL,
    )


def build_workspace_analytics_context(workspace):
    start = timezone.now() - timezone.timedelta(days=7)
    bot_types = (ClickEvent.BotClassification.KNOWN_BOT, ClickEvent.BotClassification.LIKELY_BOT)
    links = list(
        workspace.links.annotate(
            clicks_7d=Count("clicks", filter=Q(clicks__clicked_at__gte=start)),
            human_clicks_7d=Count("clicks", filter=Q(clicks__clicked_at__gte=start, clicks__bot_classification=ClickEvent.BotClassification.HUMAN)),
            bot_clicks_7d=Count("clicks", filter=Q(clicks__clicked_at__gte=start, clicks__bot_classification__in=bot_types)),
            conversions_7d=Count("conversions", filter=Q(conversions__created_at__gte=start)),
        ).values("shorturl", "campaign__name", "clicks_7d", "human_clicks_7d", "bot_clicks_7d", "conversions_7d")
    )
    devices = list(
        ClickEvent.objects.filter(short_url__workspace=workspace, clicked_at__gte=start)
        .values("device_type")
        .annotate(clicks=Count("id"))
        .order_by("-clicks")
    )
    daily = list(
        ClickEvent.objects.filter(short_url__workspace=workspace, clicked_at__gte=start)
        .annotate(day=TruncDate("clicked_at"))
        .values("day")
        .annotate(clicks=Count("id"))
        .order_by("day")
    )
    return {
        "workspace": workspace.name,
        "period": "last_7_days",
        "links": links,
        "device_breakdown": devices,
        "daily_clicks": daily,
        "conversion_count": ConversionEvent.objects.filter(link__workspace=workspace, created_at__gte=start).count(),
    }


def build_abuse_context(link):
    start = timezone.now() - timezone.timedelta(hours=24)
    recent = link.clicks.filter(clicked_at__gte=start)
    bot_count = recent.filter(
        bot_classification__in=(ClickEvent.BotClassification.KNOWN_BOT, ClickEvent.BotClassification.LIKELY_BOT)
    ).count()
    return {
        "link": link.shorturl,
        "workspace": link.workspace.name if link.workspace else None,
        "safety_status": link.safety_status,
        "safety_detail": link.safety_detail,
        "enabled": link.is_enabled,
        "reports": list(link.abuse_reports.values("reason", "status", "created_at")[:20]),
        "recent_24h_clicks": recent.count(),
        "recent_24h_bot_clicks": bot_count,
        "bot_ratio": round(bot_count / recent.count(), 3) if recent.count() else 0,
        "recent_countries": list(recent.exclude(country_code="").values("country_code").annotate(clicks=Count("id")).order_by("-clicks")[:10]),
    }
