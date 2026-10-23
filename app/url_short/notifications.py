from django.conf import settings
from django.core.mail import send_mail

from .models import NotificationDelivery


def send_notification(*, event_type, recipient, subject, body, workspace=None):
    if not recipient:
        return None
    try:
        delivered = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        status = NotificationDelivery.Status.SENT if delivered == 1 else NotificationDelivery.Status.FAILED
        error = "" if delivered == 1 else "Email backend did not confirm delivery."
    except Exception as exc:
        status = NotificationDelivery.Status.FAILED
        error = str(exc)[:500]
    return NotificationDelivery.objects.create(
        workspace=workspace,
        event_type=event_type,
        recipient=recipient,
        subject=subject[:255],
        status=status,
        error=error,
    )
