from datetime import timedelta

from django.utils import timezone

from .models import Workspace


def anonymize_expired_visitor_data(now=None):
    now = now or timezone.now()
    updated = 0
    for workspace in Workspace.objects.filter(is_active=True):
        cutoff = now - timedelta(days=workspace.analytics_retention_days)
        events = workspace.links.values_list("clicks__pk", flat=True)
        from .models import ClickEvent

        updated += ClickEvent.objects.filter(
            pk__in=events,
            clicked_at__lt=cutoff,
            ip_address__isnull=False,
        ).update(ip_address=None)
    return updated
