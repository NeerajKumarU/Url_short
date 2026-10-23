from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.dateparse import parse_datetime

from .models import Campaign, CustomDomain, LinkVersion, RedirectRule


UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


def build_utm_url(destination, parameters):
    parts = urlsplit(destination)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValidationError("Enter a valid HTTP or HTTPS destination URL.")
    supplied = {key: str(parameters.get(key, "")).strip() for key in UTM_KEYS}
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in UTM_KEYS]
    query.extend((key, value) for key, value in supplied.items() if value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))


def public_url_for_link(request, link):
    if link.workspace_id:
        domain = CustomDomain.objects.filter(
            workspace_id=link.workspace_id,
            verification_status=CustomDomain.VerificationStatus.VERIFIED,
            is_active=True,
            is_default=True,
        ).only("domain").first()
        if domain:
            return f"https://{domain.domain}/{link.shorturl}"
    from django.urls import reverse

    return request.build_absolute_uri(reverse("redirect_short_url", args=[link.shorturl]))


def snapshot_link(link):
    return {
        "longurl": link.longurl,
        "campaign_id": link.campaign_id,
        "active_from": link.active_from.isoformat() if link.active_from else None,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "is_enabled": link.is_enabled,
        "utm_parameters": link.utm_parameters,
        "conversion_tracking_enabled": link.conversion_tracking_enabled,
        "approval_status": link.approval_status,
        "safety_status": link.safety_status,
        "safety_detail": link.safety_detail,
        "routing_rules": list(
            link.routing_rules.order_by("priority", "pk").values(
                "name",
                "condition_type",
                "match_value",
                "destination_url",
                "priority",
                "is_active",
            )
        ),
    }


@transaction.atomic
def create_link_version(link, changed_by=None, change_summary=""):
    latest = (
        LinkVersion.objects.select_for_update()
        .filter(link=link)
        .aggregate(value=Max("version_number"))["value"]
        or 0
    )
    return LinkVersion.objects.create(
        link=link,
        version_number=latest + 1,
        changed_by=changed_by,
        snapshot=snapshot_link(link),
        change_summary=change_summary[:255],
    )


@transaction.atomic
def rollback_link(link, version, changed_by):
    if version.link_id != link.pk:
        raise ValidationError("This version does not belong to the selected link.")
    snapshot = version.snapshot
    campaign_id = snapshot.get("campaign_id")
    if campaign_id and not Campaign.objects.filter(pk=campaign_id, workspace_id=link.workspace_id).exists():
        raise ValidationError("The historical campaign is no longer available in this workspace.")

    link.longurl = snapshot["longurl"]
    link.campaign_id = campaign_id
    link.active_from = parse_datetime(snapshot["active_from"]) if snapshot.get("active_from") else None
    link.expires_at = parse_datetime(snapshot["expires_at"]) if snapshot.get("expires_at") else None
    link.is_enabled = bool(snapshot.get("is_enabled", True))
    link.utm_parameters = snapshot.get("utm_parameters") or {}
    link.conversion_tracking_enabled = bool(snapshot.get("conversion_tracking_enabled", False))
    link.approval_status = snapshot.get("approval_status", link.approval_status)
    link.safety_status = snapshot.get("safety_status", link.safety_status)
    link.safety_detail = snapshot.get("safety_detail", link.safety_detail)
    link.save(
        update_fields=(
            "longurl",
            "campaign",
            "active_from",
            "expires_at",
            "is_enabled",
            "utm_parameters",
            "conversion_tracking_enabled",
            "approval_status",
            "safety_status",
            "safety_detail",
            "updated_at",
        )
    )
    link.routing_rules.all().delete()
    RedirectRule.objects.bulk_create(
        [RedirectRule(link=link, **rule) for rule in snapshot.get("routing_rules", [])]
    )
    return create_link_version(
        link,
        changed_by=changed_by,
        change_summary=f"Rolled back to version {version.version_number}",
    )
