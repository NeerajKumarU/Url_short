import hashlib
import hmac
import ipaddress

from django.conf import settings


def fingerprint_ip(value, namespace=""):
    """Return a stable, non-reversible fingerprint scoped to one workspace."""
    if not value:
        return ""
    try:
        normalized = str(ipaddress.ip_address(value))
    except ValueError:
        return ""
    secret = getattr(settings, "ORBITLINK_IP_FINGERPRINT_SECRET", "") or settings.SECRET_KEY
    message = f"{namespace or 'legacy'}:{normalized}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
