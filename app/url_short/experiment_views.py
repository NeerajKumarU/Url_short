from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .conversions import parse_conversion_payload, record_conversion
from .experiments import activate_experiment
from .forms import ExperimentCreateForm
from .models import Experiment, WorkspaceMembership, urlModel
from .permissions import require_link_access
from .services import record_audit
from .webhooks import queue_webhook_event


def _experiment_link(request, pk, minimum_role):
    link = get_object_or_404(urlModel.objects.select_related("workspace"), pk=pk)
    require_link_access(request.user, link, minimum_role)
    return link


@login_required
def experiment_list(request, link_pk):
    link = _experiment_link(request, link_pk, WorkspaceMembership.Role.VIEWER)
    experiments = link.experiments.prefetch_related("variants__click_events", "variants__conversions")
    return render(
        request,
        "experiments/list.html",
        {"link": link, "experiments": experiments},
    )


@login_required
def experiment_create(request, link_pk):
    link = _experiment_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    form = ExperimentCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            experiment = form.save(link=link, created_by=request.user)
        record_audit(
            action="EXPERIMENT_CREATED",
            actor=request.user,
            workspace=link.workspace,
            target=experiment,
            metadata={"link": link.shorturl},
        )
        messages.success(request, "Experiment created as a draft. Activate it after review.")
        return redirect("experiment_list", link_pk=link.pk)
    return render(request, "experiments/form.html", {"link": link, "form": form})


@login_required
@require_POST
def experiment_activate(request, link_pk, pk):
    link = _experiment_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    experiment = get_object_or_404(Experiment, pk=pk, link=link)
    try:
        activate_experiment(experiment)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        record_audit(
            action="EXPERIMENT_ACTIVATED",
            actor=request.user,
            workspace=link.workspace,
            target=experiment,
            metadata={"link": link.shorturl},
        )
        messages.success(request, "Experiment activated.")
    return redirect("experiment_list", link_pk=link.pk)


@login_required
@require_POST
def experiment_pause(request, link_pk, pk):
    link = _experiment_link(request, link_pk, WorkspaceMembership.Role.EDITOR)
    experiment = get_object_or_404(Experiment, pk=pk, link=link)
    experiment.status = Experiment.Status.PAUSED
    experiment.save(update_fields=("status", "updated_at"))
    record_audit(
        action="EXPERIMENT_PAUSED",
        actor=request.user,
        workspace=link.workspace,
        target=experiment,
        metadata={"link": link.shorturl},
    )
    messages.success(request, "Experiment paused.")
    return redirect("experiment_list", link_pk=link.pk)


@csrf_exempt
@require_POST
def conversion_collect(request):
    try:
        payload = parse_conversion_payload(request)
        event, created = record_conversion(
            token=payload.get("token", ""),
            event_type=payload.get("event_type", ""),
            custom_name=payload.get("custom_name", ""),
            monetary_value=payload.get("monetary_value"),
            currency=payload.get("currency", ""),
            deduplication_key=payload.get("deduplication_key", ""),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
    if created and event.link_id and event.link.workspace_id:
        queue_webhook_event(
            event.link.workspace,
            "CONVERSION_RECEIVED",
            {
                "conversion_id": event.pk,
                "link_id": event.link_id,
                "event_type": event.event_type,
            },
        )
    return JsonResponse(
        {"ok": True, "conversion_id": event.pk, "created": created},
        status=201 if created else 200,
    )
