import re
import ipaddress
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


RESERVED_ALIASES = frozenset(
    {
        "admin",
        "login",
        "logout",
        "register",
        "dashboard",
        "admin-dashboard",
        "workspaces",
        "campaigns",
        "domains",
        "tools",
        "api",
        "ai",
        "analytics",
        "approvals",
        "governance",
        "report",
        "integrations",
        "exports",
        "audit",
        "health",
        "links",
        "ready",
        "metrics",
        "shorturl",
        "static",
        "media",
    }
)

ALIAS_PATTERN = re.compile(r"^[a-z0-9_-]{3,50}$")
DOMAIN_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_and_validate_alias(value):
    alias = (value or "").strip().lower()
    if not ALIAS_PATTERN.fullmatch(alias):
        raise ValidationError(
            "Use 3-50 characters containing only letters, numbers, hyphens, or underscores."
        )
    if alias in RESERVED_ALIASES:
        raise ValidationError("This alias is reserved. Please choose another one.")
    return alias


def normalize_and_validate_domain(value):
    raw = (value or "").strip().lower().rstrip(".")
    if "://" in raw or "/" in raw or "@" in raw:
        raise ValidationError("Enter only a hostname, without a scheme, path, or credentials.")
    try:
        port = urlsplit(f"//{raw}").port
    except ValueError as exc:
        raise ValidationError("Enter a valid domain name without a port.") from exc
    if port is not None:
        raise ValidationError("Custom domains cannot include a port.")
    try:
        domain = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("Enter a valid domain name.") from exc
    if len(domain) > 253 or "." not in domain:
        raise ValidationError("Enter a fully qualified domain such as go.example.com.")
    if domain == "localhost" or domain.endswith(".localhost"):
        raise ValidationError("Localhost cannot be registered as a custom domain.")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValidationError("IP addresses cannot be registered as custom domains.")
    if any(not DOMAIN_LABEL_PATTERN.fullmatch(label) for label in domain.split(".")):
        raise ValidationError("Enter a valid domain name.")
    return domain
