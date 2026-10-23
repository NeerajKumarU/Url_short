import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

from .models import urlModel


@dataclass(frozen=True)
class DestinationAssessment:
    status: str
    detail: str
    block_creation: bool = False


def _blocked_domains():
    return {
        item.strip().lower().rstrip(".")
        for item in os.environ.get("ORBITLINK_BLOCKED_DOMAINS", "").split(",")
        if item.strip()
    }


def assess_destination(destination):
    parts = urlsplit(destination)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return DestinationAssessment(
            urlModel.SafetyStatus.MALICIOUS,
            "Only HTTP and HTTPS destinations with a hostname are allowed.",
            True,
        )
    if parts.username or parts.password:
        return DestinationAssessment(
            urlModel.SafetyStatus.SUSPICIOUS,
            "Destination URLs cannot contain embedded credentials.",
            True,
        )

    hostname = parts.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        return DestinationAssessment(
            urlModel.SafetyStatus.SUSPICIOUS,
            "Local and internal hostnames are not allowed.",
            True,
        )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        return DestinationAssessment(
            urlModel.SafetyStatus.SUSPICIOUS,
            "Private, loopback, link-local, and reserved IP destinations are not allowed.",
            True,
        )

    blocked = _blocked_domains()
    if any(hostname == domain or hostname.endswith(f".{domain}") for domain in blocked):
        return DestinationAssessment(
            urlModel.SafetyStatus.MALICIOUS,
            "The destination hostname is on the configured platform block list.",
            True,
        )
    if hostname.startswith("xn--") or ".xn--" in hostname:
        return DestinationAssessment(
            urlModel.SafetyStatus.SUSPICIOUS,
            "Internationalized hostname requires manual review.",
        )
    return DestinationAssessment(
        urlModel.SafetyStatus.UNKNOWN,
        "No external threat-intelligence provider is configured; no safe verdict is claimed.",
    )


def validate_public_destination(destination):
    assessment = assess_destination(destination)
    if assessment.block_creation:
        raise ValidationError(assessment.detail)
    return destination
