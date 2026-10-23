import ipaddress
from urllib.parse import urlparse

from django.conf import settings


def classify_browser(user_agent):
    value = (user_agent or "").lower()
    if "edg/" in value or "edge/" in value:
        return "Edge"
    if "firefox/" in value or "fxios/" in value:
        return "Firefox"
    if "chrome/" in value or "crios/" in value:
        return "Chrome"
    if "safari/" in value:
        return "Safari"
    return "Other"


def classify_device(user_agent):
    value = (user_agent or "").lower()
    if any(token in value for token in ("ipad", "tablet", "kindle")):
        return "Tablet"
    if any(token in value for token in ("mobile", "iphone", "android")):
        return "Mobile"
    if any(token in value for token in ("windows", "macintosh", "linux", "x11")):
        return "Desktop"
    return "Other"


def classify_operating_system(user_agent):
    value = (user_agent or "").lower()
    if "android" in value:
        return "Android"
    if any(token in value for token in ("iphone", "ipad", "ipod")):
        return "iOS"
    if "windows" in value:
        return "Windows"
    if "macintosh" in value or "mac os x" in value:
        return "macOS"
    if "linux" in value or "x11" in value:
        return "Linux"
    return "Other"


def classify_referrer(referrer):
    if not referrer:
        return "Direct"
    hostname = (urlparse(referrer).hostname or "").lower()
    if "instagram.com" in hostname:
        return "Instagram"
    if "google." in hostname:
        return "Google"
    if "linkedin.com" in hostname or "lnkd.in" in hostname:
        return "LinkedIn"
    return "Other"


def event_details(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
    referrer = request.META.get("HTTP_REFERER", "")[:2048]
    remote_address = request.META.get("REMOTE_ADDR")
    try:
        ip_address = str(ipaddress.ip_address(remote_address)) if remote_address else None
    except ValueError:
        ip_address = None
    country_code = ""
    region = ""
    city = ""
    if settings.ORBITLINK_TRUST_CLOUDFLARE_GEO:
        candidate = request.META.get("HTTP_CF_IPCOUNTRY", "").upper()
        country_code = candidate if len(candidate) == 2 and candidate.isalpha() else ""
        region = request.META.get("HTTP_CF_REGION", "")[:100]
        city = request.META.get("HTTP_CF_IPCITY", "")[:100]
    return {
        # REMOTE_ADDR is intentionally used instead of trusting a client-supplied
        # X-Forwarded-For header. Deployments can add trusted-proxy handling later.
        "ip_address": ip_address if settings.ORBITLINK_STORE_VISITOR_IPS else None,
        "user_agent": user_agent,
        "referrer": referrer,
        "browser": classify_browser(user_agent),
        "device_type": classify_device(user_agent),
        "operating_system": classify_operating_system(user_agent),
        "referrer_source": classify_referrer(referrer),
        "country_code": country_code,
        "region": region,
        "city": city,
    }
