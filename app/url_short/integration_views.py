import csv
import io
import json
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .api_keys import authenticate_api_key, bearer_token, create_api_credential
from .forms import ApiCredentialForm, BulkImportForm, ShortUrlForm, WebhookEndpointForm
from .link_services import create_link_version
from .models import ApiCredential, Campaign, WebhookDelivery, WebhookEndpoint, WorkspaceMembership, urlModel
from .permissions import require_workspace_role
from .security import assess_destination, validate_public_destination
from .selectors import get_current_workspace
from .services import record_audit
from .validators import normalize_and_validate_alias
from .webhooks import create_webhook_endpoint, deliver_webhook, queue_webhook_event


def _automatic_alias():
    for _ in range(30):
        alias = secrets.token_urlsafe(6).replace("_", "").replace("-", "").lower()[:8]
        if len(alias) >= 3 and not urlModel.objects.filter(shorturl=alias).exists():
            return alias
    raise RuntimeError("Unable to allocate a unique alias.")


def _csv_safe(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


@login_required
def api_key_list(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    raw_key = request.session.pop("new_api_key", None)
    return render(
        request,
        "integrations/api_keys.html",
        {
            "workspace": workspace,
            "credentials": workspace.api_credentials.select_related("created_by"),
            "form": ApiCredentialForm(),
            "raw_key": raw_key,
        },
    )


@login_required
@require_POST
def api_key_create(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    form = ApiCredentialForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "integrations/api_keys.html",
            {"workspace": workspace, "credentials": workspace.api_credentials.all(), "form": form},
            status=400,
        )
    credential, raw_key = create_api_credential(
        workspace=workspace,
        name=form.cleaned_data["name"],
        scopes=form.cleaned_data["scopes"],
        created_by=request.user,
        expires_at=form.cleaned_data.get("expires_at"),
    )
    request.session["new_api_key"] = raw_key
    record_audit(action="API_KEY_CREATED", actor=request.user, workspace=workspace, target=credential)
    messages.success(request, "API key created. Copy it now; it will not be shown again.")
    return redirect("api_key_list")


@login_required
@require_POST
def api_key_revoke(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    credential = get_object_or_404(ApiCredential, pk=pk, workspace=workspace)
    if credential.revoked_at is None:
        credential.revoked_at = timezone.now()
        credential.save(update_fields=("revoked_at",))
        record_audit(action="API_KEY_REVOKED", actor=request.user, workspace=workspace, target=credential)
    messages.success(request, "API key revoked.")
    return redirect("api_key_list")


@login_required
def webhook_list(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    raw_secret = request.session.pop("new_webhook_secret", None)
    return render(
        request,
        "integrations/webhooks.html",
        {
            "workspace": workspace,
            "endpoints": workspace.webhook_endpoints.prefetch_related("deliveries"),
            "form": WebhookEndpointForm(),
            "raw_secret": raw_secret,
        },
    )


@login_required
@require_POST
def webhook_create(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    form = WebhookEndpointForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "integrations/webhooks.html",
            {"workspace": workspace, "endpoints": workspace.webhook_endpoints.all(), "form": form},
            status=400,
        )
    endpoint, raw_secret = create_webhook_endpoint(
        workspace=workspace,
        name=form.cleaned_data["name"],
        endpoint_url=form.cleaned_data["endpoint_url"],
        subscribed_events=form.cleaned_data["subscribed_events"],
        created_by=request.user,
        is_active=form.cleaned_data["is_active"],
    )
    request.session["new_webhook_secret"] = raw_secret
    record_audit(action="WEBHOOK_CREATED", actor=request.user, workspace=workspace, target=endpoint)
    messages.success(request, "Webhook created. Copy its signing secret now.")
    return redirect("webhook_list")


@login_required
@require_POST
def webhook_toggle(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    endpoint = get_object_or_404(WebhookEndpoint, pk=pk, workspace=workspace)
    endpoint.is_active = not endpoint.is_active
    endpoint.save(update_fields=("is_active", "updated_at"))
    record_audit(action="WEBHOOK_TOGGLED", actor=request.user, workspace=workspace, target=endpoint, metadata={"active": endpoint.is_active})
    return redirect("webhook_list")


@login_required
@require_POST
def webhook_retry(request, pk):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.ADMIN)
    delivery = get_object_or_404(WebhookDelivery.objects.select_related("endpoint"), pk=pk, endpoint__workspace=workspace)
    deliver_webhook(delivery)
    messages.success(request, f"Webhook attempt finished with status {delivery.get_status_display()}.")
    return redirect("webhook_list")


@login_required
@require_http_methods(["GET", "POST"])
def bulk_import(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.EDITOR)
    form = BulkImportForm(request.POST or None, request.FILES or None)
    row_errors = []
    if request.method == "POST" and form.is_valid():
        try:
            content = form.cleaned_data["csv_file"].read().decode("utf-8-sig")
        except UnicodeDecodeError:
            form.add_error("csv_file", "CSV must use UTF-8 encoding.")
        else:
            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames or "destination" not in {name.strip().lower() for name in reader.fieldnames}:
                form.add_error("csv_file", "CSV must contain a destination column.")
            else:
                normalized_rows = []
                seen_aliases = set()
                campaigns = {item.name.casefold(): item for item in workspace.campaigns.all()}
                for row_number, source in enumerate(reader, start=2):
                    row = {(key or "").strip().lower(): (value or "").strip() for key, value in source.items()}
                    errors = []
                    destination = row.get("destination", "")
                    try:
                        validate_public_destination(destination)
                    except Exception as exc:
                        errors.extend(getattr(exc, "messages", [str(exc)]))
                    alias = row.get("alias", "")
                    if alias:
                        try:
                            alias = normalize_and_validate_alias(alias)
                        except Exception as exc:
                            errors.extend(getattr(exc, "messages", [str(exc)]))
                        if alias in seen_aliases or urlModel.objects.filter(shorturl__iexact=alias).exists():
                            errors.append("Alias is duplicated or already in use.")
                        seen_aliases.add(alias)
                    campaign_name = row.get("campaign", "")
                    campaign = campaigns.get(campaign_name.casefold()) if campaign_name else None
                    if campaign_name and campaign is None:
                        errors.append("Campaign was not found in this workspace.")
                    if errors:
                        row_errors.append({"row": row_number, "errors": errors})
                    else:
                        normalized_rows.append((destination, alias, campaign))
                if not row_errors and normalized_rows:
                    with transaction.atomic():
                        for destination, alias, campaign in normalized_rows:
                            safety = assess_destination(destination)
                            link = urlModel.objects.create(
                                workspace=workspace,
                                owner=request.user,
                                campaign=campaign,
                                longurl=destination,
                                shorturl=alias or _automatic_alias(),
                                safety_status=safety.status,
                                safety_detail=safety.detail,
                                safety_checked_at=timezone.now(),
                            )
                            create_link_version(link, request.user, "Imported from CSV")
                            record_audit(action="LINK_IMPORTED", actor=request.user, workspace=workspace, target=link)
                            queue_webhook_event(workspace, "LINK_CREATED", {"link_id": link.pk, "alias": link.shorturl})
                    messages.success(request, f"Imported {len(normalized_rows)} links.")
                    return redirect("dashboard")
                if not row_errors and not normalized_rows:
                    form.add_error("csv_file", "CSV contains no data rows.")
    return render(request, "integrations/bulk_import.html", {"workspace": workspace, "form": form, "row_errors": row_errors})


@login_required
def export_links(request):
    workspace = get_current_workspace(request)
    require_workspace_role(request.user, workspace, WorkspaceMembership.Role.VIEWER)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="orbitlink-links.csv"'
    writer = csv.writer(response)
    writer.writerow(("alias", "destination", "campaign", "status", "clicks", "created_at"))
    for link in workspace.links.select_related("campaign").order_by("pk"):
        writer.writerow(tuple(_csv_safe(value) for value in (link.shorturl, link.longurl, link.campaign.name if link.campaign else "", link.status_label, link.count, link.created_at.isoformat())))
    return response


def _api_error(message, status):
    return JsonResponse({"error": message}, status=status)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_links(request):
    required_scope = "links:read" if request.method == "GET" else "links:write"
    credential, error = authenticate_api_key(bearer_token(request), required_scope)
    if error:
        status = 403 if error.startswith("Missing required scope") else 401
        return _api_error(error, status)
    workspace = credential.workspace
    if request.method == "GET":
        links = workspace.links.order_by("-created_at")[:200]
        return JsonResponse({"results": [{"id": link.pk, "alias": link.shorturl, "destination": link.longurl, "status": link.status_label, "clicks": link.count} for link in links]})
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return _api_error("Request body must be valid JSON.", 400)
    form = ShortUrlForm({"longurl": payload.get("destination", ""), "custom_alias": payload.get("alias", "")}, workspace=workspace)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    safety = assess_destination(form.cleaned_data["longurl"])
    try:
        link = urlModel.objects.create(
            workspace=workspace,
            owner=credential.created_by,
            longurl=form.cleaned_data["longurl"],
            shorturl=form.cleaned_data["custom_alias"] or _automatic_alias(),
            safety_status=safety.status,
            safety_detail=safety.detail,
            safety_checked_at=timezone.now(),
        )
    except IntegrityError:
        return _api_error("Alias is already in use.", 409)
    create_link_version(link, credential.created_by, "Created through API")
    record_audit(action="LINK_CREATED_API", actor=credential.created_by, workspace=workspace, target=link, metadata={"api_key_prefix": credential.prefix})
    queue_webhook_event(workspace, "LINK_CREATED", {"link_id": link.pk, "alias": link.shorturl})
    return JsonResponse({"id": link.pk, "alias": link.shorturl, "destination": link.longurl}, status=201)
