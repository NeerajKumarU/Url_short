import hashlib
import hmac
import json
import secrets
import ipaddress
import socket
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import WebhookDelivery, WebhookEndpoint


def _secret_from_seed(seed):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        seed.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@transaction.atomic
def create_webhook_endpoint(*, workspace, name, endpoint_url, subscribed_events, created_by, is_active=True):
    seed = secrets.token_urlsafe(32)
    secret = _secret_from_seed(seed)
    endpoint = WebhookEndpoint.objects.create(
        workspace=workspace,
        name=name,
        endpoint_url=endpoint_url,
        secret_seed=seed,
        secret_prefix=secret[:8],
        subscribed_events=sorted(set(subscribed_events)),
        created_by=created_by,
        is_active=is_active,
    )
    return endpoint, secret


def serialize_webhook_payload(delivery):
    envelope = {
        "id": str(delivery.event_id),
        "event": delivery.event_type,
        "created_at": delivery.created_at.isoformat(),
        "data": delivery.payload,
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signature_for_delivery(delivery):
    body = serialize_webhook_payload(delivery)
    secret = _secret_from_seed(delivery.endpoint.secret_seed)
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def queue_webhook_event(workspace, event_type, payload):
    endpoints = WebhookEndpoint.objects.filter(workspace=workspace, is_active=True)
    deliveries = [
        WebhookDelivery(endpoint=endpoint, event_type=event_type, payload=payload)
        for endpoint in endpoints
        if event_type in endpoint.subscribed_events
    ]
    return WebhookDelivery.objects.bulk_create(deliveries)


def deliver_webhook(delivery, timeout=5):
    if not delivery.endpoint.is_active:
        return delivery
    body = serialize_webhook_payload(delivery)
    signature = signature_for_delivery(delivery)
    hostname = urlsplit(delivery.endpoint.endpoint_url).hostname
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except (socket.gaierror, ValueError, TypeError) as exc:
        addresses = set()
        resolution_error = exc
    else:
        resolution_error = None
    if not addresses or any(not address.is_global for address in addresses):
        delivery.attempt_count += 1
        delivery.last_attempt_at = timezone.now()
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.response_body = (
            f"Endpoint DNS resolution failed: {resolution_error}"
            if resolution_error
            else "Endpoint resolves to a private, local, or reserved address."
        )[:1000]
        delivery.next_retry_at = None
        delivery.save(update_fields=("attempt_count", "last_attempt_at", "status", "response_body", "next_retry_at"))
        return delivery
    request = Request(
        delivery.endpoint.endpoint_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "OrbitLink-Webhooks/1.0",
            "X-OrbitLink-Event": delivery.event_type,
            "X-OrbitLink-Delivery": str(delivery.event_id),
            "X-OrbitLink-Signature": f"sha256={signature}",
        },
    )
    delivery.attempt_count += 1
    delivery.last_attempt_at = timezone.now()
    try:
        with urlopen(request, timeout=timeout) as response:
            delivery.response_code = response.status
            delivery.response_body = response.read(1000).decode("utf-8", errors="replace")
        if 200 <= delivery.response_code < 300:
            delivery.status = WebhookDelivery.Status.SUCCEEDED
            delivery.delivered_at = timezone.now()
            delivery.next_retry_at = None
        else:
            raise HTTPError(request.full_url, delivery.response_code, "Webhook rejected", {}, None)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, HTTPError):
            delivery.response_code = exc.code
        delivery.response_body = str(exc)[:1000]
        delivery.status = WebhookDelivery.Status.RETRYING if delivery.attempt_count < 5 else WebhookDelivery.Status.FAILED
        delivery.next_retry_at = (
            timezone.now() + timedelta(minutes=min(2 ** delivery.attempt_count, 60))
            if delivery.attempt_count < 5
            else None
        )
    delivery.save(
        update_fields=(
            "attempt_count",
            "last_attempt_at",
            "response_code",
            "response_body",
            "status",
            "delivered_at",
            "next_retry_at",
        )
    )
    return delivery
