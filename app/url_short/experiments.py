import hashlib
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Experiment, ExperimentVariant


VISITOR_COOKIE = "orbitlink_visitor"


@dataclass(frozen=True)
class ExperimentAssignment:
    variant: ExperimentVariant
    new_visitor_id: str | None = None


def validate_experiment_weights(experiment):
    weights = list(experiment.variants.values_list("weight", flat=True))
    if len(weights) < 2:
        raise ValidationError("An experiment requires at least two variants.")
    if sum(weights) != 100:
        raise ValidationError("Variant weights must total exactly 100.")


@transaction.atomic
def activate_experiment(experiment):
    validate_experiment_weights(experiment)
    if Experiment.objects.filter(link=experiment.link, status=Experiment.Status.ACTIVE).exclude(
        pk=experiment.pk
    ).exists():
        raise ValidationError("This link already has an active experiment.")
    experiment.status = Experiment.Status.ACTIVE
    experiment.save(update_fields=("status", "updated_at"))
    return experiment


def _bucket_for(experiment, visitor_id):
    material = f"{settings.SECRET_KEY}:{experiment.pk}:{visitor_id}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % 100


def _variant_for_bucket(variants, bucket):
    upper = 0
    for variant in variants:
        upper += variant.weight
        if bucket < upper:
            return variant
    return variants[-1]


def select_experiment_variant(link, request, *, now=None):
    now = now or timezone.now()
    experiment = (
        link.experiments.filter(status=Experiment.Status.ACTIVE)
        .prefetch_related("variants")
        .first()
    )
    if experiment is None:
        return None
    if experiment.start_at and experiment.start_at > now:
        return None
    if experiment.end_at and experiment.end_at < now:
        return None
    variants = list(experiment.variants.all())
    if len(variants) < 2 or sum(variant.weight for variant in variants) != 100:
        return None

    if experiment.assignment_strategy == Experiment.AssignmentStrategy.RANDOM:
        return ExperimentAssignment(_variant_for_bucket(variants, secrets.randbelow(100)))

    visitor_id = request.COOKIES.get(VISITOR_COOKIE, "")
    new_visitor_id = None
    if not visitor_id or len(visitor_id) > 128:
        visitor_id = secrets.token_urlsafe(24)
        new_visitor_id = visitor_id
    return ExperimentAssignment(
        _variant_for_bucket(variants, _bucket_for(experiment, visitor_id)),
        new_visitor_id,
    )


def set_assignment_cookie(response, visitor_id, request):
    if visitor_id:
        response.set_cookie(
            VISITOR_COOKIE,
            visitor_id,
            max_age=365 * 24 * 60 * 60,
            secure=request.is_secure(),
            httponly=True,
            samesite="Lax",
        )
