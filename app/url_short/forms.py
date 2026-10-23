from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .link_services import UTM_KEYS, build_utm_url
from .models import (
    ApiCredential,
    Campaign,
    AbuseReport,
    CustomDomain,
    Experiment,
    ExperimentVariant,
    RedirectRule,
    Workspace,
    WebhookEndpoint,
    urlModel,
)
from .validators import normalize_and_validate_alias, normalize_and_validate_domain
from .security import validate_public_destination


DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


class FutureExpiryMixin:
    def clean_expires_at(self):
        expires_at = self.cleaned_data.get("expires_at")
        if expires_at and expires_at <= timezone.now():
            raise forms.ValidationError("Expiry must be a future date and time.")
        return expires_at


class ShortUrlForm(FutureExpiryMixin, forms.Form):
    longurl = forms.URLField(label="Original URL", max_length=255)
    custom_alias = forms.CharField(
        label="Custom alias (optional)",
        required=False,
        min_length=3,
        max_length=50,
        help_text="Leave blank to generate one automatically.",
    )
    expires_at = forms.DateTimeField(
        label="Expiry date and time (optional)",
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_LOCAL_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )
    active_from = forms.DateTimeField(
        label="Activation date and time (optional)",
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.none(),
        required=False,
        empty_label="No campaign",
    )
    conversion_tracking_enabled = forms.BooleanField(
        required=False,
        label="Enable conversion-token attribution",
    )

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace is not None:
            self.fields["campaign"].queryset = Campaign.objects.filter(workspace=workspace)

    def clean_custom_alias(self):
        value = self.cleaned_data.get("custom_alias")
        if not value:
            return ""
        alias = normalize_and_validate_alias(value)
        if urlModel.objects.filter(shorturl__iexact=alias).exists():
            raise forms.ValidationError("This alias is already taken.")
        return alias

    def clean_longurl(self):
        return validate_public_destination(self.cleaned_data["longurl"])

    def clean(self):
        cleaned = super().clean()
        active_from = cleaned.get("active_from")
        expires_at = cleaned.get("expires_at")
        if active_from and expires_at and expires_at <= active_from:
            self.add_error("expires_at", "Expiry must be after the activation time.")
        return cleaned


class LinkEditForm(FutureExpiryMixin, forms.ModelForm):
    active_from = forms.DateTimeField(
        label="Activation date and time (optional)",
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )
    expires_at = forms.DateTimeField(
        label="Expiry date and time (optional)",
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_LOCAL_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        model = urlModel
        fields = (
            "longurl",
            "campaign",
            "active_from",
            "expires_at",
            "is_enabled",
            "conversion_tracking_enabled",
        )
        labels = {"longurl": "Destination URL"}

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = workspace or getattr(self.instance, "workspace", None)
        self.fields["campaign"].queryset = (
            Campaign.objects.filter(workspace=workspace) if workspace else Campaign.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        active_from = cleaned.get("active_from")
        expires_at = cleaned.get("expires_at")
        if active_from and expires_at and expires_at <= active_from:
            self.add_error("expires_at", "Expiry must be after the activation time.")
        return cleaned

    def clean_longurl(self):
        return validate_public_destination(self.cleaned_data["longurl"])


class CampaignForm(forms.ModelForm):
    start_at = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )
    end_at = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = Campaign
        fields = ("name", "description", "status", "start_at", "end_at")

    def clean(self):
        cleaned = super().clean()
        start_at = cleaned.get("start_at")
        end_at = cleaned.get("end_at")
        if start_at and end_at and end_at < start_at:
            self.add_error("end_at", "End date must be after the start date.")
        return cleaned


class CustomDomainForm(forms.ModelForm):
    class Meta:
        model = CustomDomain
        fields = ("domain", "is_default")

    def clean_domain(self):
        domain = normalize_and_validate_domain(self.cleaned_data["domain"])
        query = CustomDomain.objects.filter(domain__iexact=domain)
        if self.instance.pk:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("This domain has already been claimed.")
        return domain


class RedirectRuleForm(forms.ModelForm):
    class Meta:
        model = RedirectRule
        fields = (
            "name",
            "condition_type",
            "match_value",
            "destination_url",
            "priority",
            "is_active",
        )

    def clean(self):
        cleaned = super().clean()
        condition = cleaned.get("condition_type")
        value = (cleaned.get("match_value") or "").strip()
        if condition != RedirectRule.ConditionType.DEFAULT and not value:
            self.add_error("match_value", "A match value is required for this condition.")
        if condition == RedirectRule.ConditionType.DEFAULT:
            cleaned["match_value"] = ""
        return cleaned

    def clean_destination_url(self):
        return validate_public_destination(self.cleaned_data["destination_url"])


class UtmBuilderForm(forms.Form):
    destination = forms.URLField(max_length=2048)
    utm_source = forms.CharField(max_length=200, required=False)
    utm_medium = forms.CharField(max_length=200, required=False)
    utm_campaign = forms.CharField(max_length=200, required=False)
    utm_term = forms.CharField(max_length=200, required=False)
    utm_content = forms.CharField(max_length=200, required=False)

    def build_url(self):
        if not self.is_valid():
            raise ValueError("Validate the form before building a URL.")
        parameters = {key: self.cleaned_data.get(key, "") for key in UTM_KEYS}
        return build_utm_url(self.cleaned_data["destination"], parameters)


class ExperimentCreateForm(forms.Form):
    name = forms.CharField(max_length=160)
    assignment_strategy = forms.ChoiceField(choices=Experiment.AssignmentStrategy.choices)
    start_at = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )
    end_at = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )
    variant_a_name = forms.CharField(max_length=80, initial="Variant A")
    variant_a_url = forms.URLField(max_length=2048)
    variant_a_weight = forms.IntegerField(min_value=1, max_value=99, initial=50)
    variant_b_name = forms.CharField(max_length=80, initial="Variant B")
    variant_b_url = forms.URLField(max_length=2048)
    variant_b_weight = forms.IntegerField(min_value=1, max_value=99, initial=50)

    def clean(self):
        cleaned = super().clean()
        start_at = cleaned.get("start_at")
        end_at = cleaned.get("end_at")
        if start_at and end_at and end_at < start_at:
            self.add_error("end_at", "End date must be after the start date.")
        weight_a = cleaned.get("variant_a_weight")
        weight_b = cleaned.get("variant_b_weight")
        if weight_a is not None and weight_b is not None and weight_a + weight_b != 100:
            raise forms.ValidationError("Variant weights must total exactly 100.")
        if cleaned.get("variant_a_name") == cleaned.get("variant_b_name"):
            raise forms.ValidationError("Variant names must be different.")
        return cleaned

    def clean_variant_a_url(self):
        return validate_public_destination(self.cleaned_data["variant_a_url"])

    def clean_variant_b_url(self):
        return validate_public_destination(self.cleaned_data["variant_b_url"])

    def save(self, *, link, created_by):
        experiment = Experiment.objects.create(
            link=link,
            name=self.cleaned_data["name"],
            assignment_strategy=self.cleaned_data["assignment_strategy"],
            start_at=self.cleaned_data.get("start_at"),
            end_at=self.cleaned_data.get("end_at"),
            created_by=created_by,
        )
        ExperimentVariant.objects.bulk_create(
            [
                ExperimentVariant(
                    experiment=experiment,
                    name=self.cleaned_data["variant_a_name"],
                    destination_url=self.cleaned_data["variant_a_url"],
                    weight=self.cleaned_data["variant_a_weight"],
                ),
                ExperimentVariant(
                    experiment=experiment,
                    name=self.cleaned_data["variant_b_name"],
                    destination_url=self.cleaned_data["variant_b_url"],
                    weight=self.cleaned_data["variant_b_weight"],
                ),
            ]
        )
        return experiment


class AbuseReportForm(forms.ModelForm):
    class Meta:
        model = AbuseReport
        fields = ("reason", "details", "reporter_email")
        widgets = {"details": forms.Textarea(attrs={"rows": 5})}


class ApprovalReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=(("approve", "Approve"), ("reject", "Reject")))
    comment = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))


class WorkspaceGovernanceForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ("require_link_approval", "analytics_retention_days")

    def clean_analytics_retention_days(self):
        value = self.cleaned_data["analytics_retention_days"]
        if not 7 <= value <= 730:
            raise forms.ValidationError("Choose a retention period from 7 to 730 days.")
        return value


API_SCOPE_CHOICES = (
    ("links:read", "Read links"),
    ("links:write", "Create links"),
    ("analytics:read", "Read analytics"),
    ("campaigns:write", "Manage campaigns"),
)


class ApiCredentialForm(forms.ModelForm):
    scopes = forms.MultipleChoiceField(
        choices=API_SCOPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    expires_at = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(format=DATETIME_LOCAL_FORMAT, attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = ApiCredential
        fields = ("name", "scopes", "expires_at")

    def clean_expires_at(self):
        value = self.cleaned_data.get("expires_at")
        if value and value <= timezone.now():
            raise forms.ValidationError("Expiry must be a future date and time.")
        return value


WEBHOOK_EVENT_CHOICES = (
    ("LINK_CREATED", "Link created"),
    ("LINK_UPDATED", "Link updated"),
    ("LINK_EXPIRED", "Link expired"),
    ("CLICK_THRESHOLD_REACHED", "Click threshold reached"),
    ("CONVERSION_RECEIVED", "Conversion received"),
    ("TRAFFIC_SPIKE", "Traffic spike"),
    ("LINK_BLOCKED", "Link blocked"),
)


class WebhookEndpointForm(forms.ModelForm):
    subscribed_events = forms.MultipleChoiceField(
        choices=WEBHOOK_EVENT_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = WebhookEndpoint
        fields = ("name", "endpoint_url", "subscribed_events", "is_active")

    def clean_endpoint_url(self):
        return validate_public_destination(self.cleaned_data["endpoint_url"])


class BulkImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text="UTF-8 CSV, maximum 1 MB. Required columns: destination. Optional: alias, campaign."
    )

    def clean_csv_file(self):
        upload = self.cleaned_data["csv_file"]
        if upload.size > 1024 * 1024:
            raise forms.ValidationError("CSV files must be 1 MB or smaller.")
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Upload a .csv file.")
        return upload


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
