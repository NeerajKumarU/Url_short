from dataclasses import dataclass

from .models import ClickEvent


KNOWN_BOT_MARKERS = (
    "googlebot",
    "bingbot",
    "duckduckbot",
    "yandexbot",
    "baiduspider",
    "facebookexternalhit",
    "linkedinbot",
    "slackbot",
)
LIKELY_BOT_MARKERS = (
    "crawler",
    "spider",
    "headlesschrome",
    "phantomjs",
    "selenium",
    "python-requests",
    "curl/",
    "wget/",
)
HUMAN_BROWSER_MARKERS = ("mozilla/", "chrome/", "safari/", "firefox/", "edg/")


@dataclass(frozen=True)
class BotAssessment:
    classification: str
    reason: str


def classify_request_bot(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
    if not user_agent:
        return BotAssessment(ClickEvent.BotClassification.UNKNOWN, "Missing User-Agent")
    marker = next((value for value in KNOWN_BOT_MARKERS if value in user_agent), None)
    if marker:
        return BotAssessment(ClickEvent.BotClassification.KNOWN_BOT, f"Known crawler marker: {marker}")
    marker = next((value for value in LIKELY_BOT_MARKERS if value in user_agent), None)
    if marker:
        return BotAssessment(ClickEvent.BotClassification.LIKELY_BOT, f"Automation marker: {marker}")
    if any(value in user_agent for value in HUMAN_BROWSER_MARKERS):
        return BotAssessment(ClickEvent.BotClassification.HUMAN, "Common interactive browser signature")
    return BotAssessment(ClickEvent.BotClassification.UNKNOWN, "No recognized browser or crawler marker")
