import json
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import ClickEvent, ConversionEvent


def destination_with_conversion_token(destination, token):
    parts = urlsplit(destination)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "ol_click"]
    query.append(("ol_click", str(token)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def parse_conversion_payload(request):
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except (TypeError, ValueError) as exc:
            raise ValidationError("Request body must contain valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")
        return payload
    return request.POST.dict()


@transaction.atomic
def record_conversion(*, token, event_type, custom_name="", monetary_value=None, currency="", deduplication_key="", metadata=None):
    try:
        click = ClickEvent.objects.select_related(
            "short_url__campaign",
            "experiment_variant",
        ).get(conversion_token=token)
    except (ClickEvent.DoesNotExist, ValueError) as exc:
        raise ValidationError("Invalid conversion token.") from exc

    valid_types = {choice for choice, _label in ConversionEvent.EventType.choices}
    if event_type not in valid_types:
        raise ValidationError("Invalid conversion event type.")
    if event_type == ConversionEvent.EventType.CUSTOM and not custom_name.strip():
        raise ValidationError("custom_name is required for CUSTOM conversions.")

    value = None
    if monetary_value not in (None, ""):
        try:
            value = Decimal(str(monetary_value))
        except InvalidOperation as exc:
            raise ValidationError("monetary_value must be a valid decimal.") from exc
        if value < 0:
            raise ValidationError("monetary_value cannot be negative.")

    safe_metadata = {
        str(key)[:80]: item
        for key, item in (metadata or {}).items()
        if item is None or isinstance(item, (str, int, float, bool))
    }
    values = {
        "click": click,
        "link": click.short_url,
        "campaign": click.short_url.campaign,
        "experiment_variant": click.experiment_variant,
        "event_type": event_type,
        "custom_name": custom_name.strip()[:100],
        "monetary_value": value,
        "currency": currency.strip().upper()[:3],
        "metadata": safe_metadata,
    }
    key = deduplication_key.strip()[:128]
    if key:
        try:
            event, created = ConversionEvent.objects.get_or_create(
                link=click.short_url,
                deduplication_key=key,
                defaults=values,
            )
        except IntegrityError:
            event = ConversionEvent.objects.get(link=click.short_url, deduplication_key=key)
            created = False
        return event, created
    return ConversionEvent.objects.create(deduplication_key="", **values), True
