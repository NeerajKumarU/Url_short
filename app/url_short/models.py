from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
import secrets
import uuid


def generate_verification_token():
    return secrets.token_urlsafe(32)


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_workspaces",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="WorkspaceMembership",
        related_name="workspaces",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    require_link_approval = models.BooleanField(default=False)
    analytics_retention_days = models.PositiveSmallIntegerField(default=90)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class WorkspaceMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        ADMIN = "ADMIN", "Admin"
        EDITOR = "EDITOR", "Editor"
        VIEWER = "VIEWER", "Viewer"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.VIEWER)
    is_active = models.BooleanField(default=True, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "user"),
                name="unique_workspace_membership",
            )
        ]
        indexes = [models.Index(fields=("user", "is_active", "role"))]
        ordering = ("workspace__name", "user__username")

    def __str__(self):
        return f"{self.user} · {self.workspace} ({self.get_role_display()})"


class CustomDomain(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        FAILED = "FAILED", "Failed"
        DISABLED = "DISABLED", "Disabled"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="custom_domains",
    )
    domain = models.CharField(max_length=253, unique=True)
    verification_status = models.CharField(
        max_length=12,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    verification_token = models.CharField(
        max_length=128,
        default=generate_verification_token,
        editable=False,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("domain",)
        constraints = [
            models.UniqueConstraint(
                fields=("workspace",),
                condition=Q(is_default=True),
                name="one_default_domain_per_workspace",
            )
        ]

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower().rstrip(".")
        super().save(*args, **kwargs)

    @property
    def dns_record_name(self):
        return f"_orbitlink-verification.{self.domain}"

    def __str__(self):
        return self.domain


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        ENDED = "ENDED", "Ended"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_campaigns",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("workspace", "status", "-created_at"))]
        constraints = [
            models.CheckConstraint(
                check=Q(start_at__isnull=True)
                | Q(end_at__isnull=True)
                | Q(end_at__gte=F("start_at")),
                name="campaign_end_not_before_start",
            )
        ]

    def __str__(self):
        return self.name


class urlModel(models.Model):
    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        DISABLED = "DISABLED", "Disabled"

    class SafetyStatus(models.TextChoices):
        SAFE = "SAFE", "Safe"
        SUSPICIOUS = "SUSPICIOUS", "Suspicious"
        MALICIOUS = "MALICIOUS", "Malicious"
        UNKNOWN = "UNKNOWN", "Unknown"
        PENDING = "PENDING", "Pending"

    longurl = models.CharField(max_length=255)
    shorturl = models.CharField(max_length=50, unique=True)
    count = models.IntegerField(default=0)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="short_urls",
    )
    workspace = models.ForeignKey(
        Workspace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="links",
    )
    campaign = models.ForeignKey(
        Campaign,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    active_from = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True, db_index=True)
    utm_parameters = models.JSONField(default=dict, blank=True)
    conversion_tracking_enabled = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        db_index=True,
    )
    safety_status = models.CharField(
        max_length=12,
        choices=SafetyStatus.choices,
        default=SafetyStatus.UNKNOWN,
        db_index=True,
    )
    safety_detail = models.CharField(max_length=500, blank=True)
    safety_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("workspace", "-created_at")),
            models.Index(fields=("campaign", "-created_at")),
        ]

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def status_label(self):
        now = timezone.now()
        if not self.is_enabled:
            return "Disabled"
        if self.approval_status != self.ApprovalStatus.APPROVED:
            return self.get_approval_status_display()
        if self.safety_status == self.SafetyStatus.MALICIOUS:
            return "Blocked"
        if self.active_from and self.active_from > now:
            return "Scheduled"
        if self.is_expired:
            return "Expired"
        return "Active"

    @property
    def is_available(self):
        return self.status_label == "Active"

    def __str__(self) -> str:
        return self.shorturl


class ClickEvent(models.Model):
    class BotClassification(models.TextChoices):
        HUMAN = "HUMAN", "Human"
        KNOWN_BOT = "KNOWN_BOT", "Known bot"
        LIKELY_BOT = "LIKELY_BOT", "Likely bot"
        UNKNOWN = "UNKNOWN", "Unknown"

    short_url = models.ForeignKey(
        urlModel,
        on_delete=models.CASCADE,
        related_name="clicks",
    )
    clicked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)
    referrer = models.CharField(max_length=2048, blank=True)
    browser = models.CharField(max_length=32, default="Other")
    device_type = models.CharField(max_length=32, default="Other")
    operating_system = models.CharField(max_length=32, default="Other")
    referrer_source = models.CharField(max_length=32, default="Direct")
    resolved_destination = models.URLField(max_length=2048, blank=True)
    routing_rule = models.ForeignKey(
        "RedirectRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clicks",
    )
    experiment_variant = models.ForeignKey(
        "ExperimentVariant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="click_events",
    )
    conversion_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    bot_classification = models.CharField(
        max_length=12,
        choices=BotClassification.choices,
        default=BotClassification.UNKNOWN,
        db_index=True,
    )
    bot_reason = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    region = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-clicked_at"]

    def __str__(self):
        return f"{self.short_url.shorturl} at {self.clicked_at:%Y-%m-%d %H:%M:%S}"


class RedirectRule(models.Model):
    class ConditionType(models.TextChoices):
        COUNTRY = "COUNTRY", "Country"
        DEVICE = "DEVICE", "Device"
        OPERATING_SYSTEM = "OPERATING_SYSTEM", "Operating system"
        BROWSER = "BROWSER", "Browser"
        LANGUAGE = "LANGUAGE", "Language"
        DATE_TIME = "DATE_TIME", "Date/time window"
        REFERRER = "REFERRER", "Referrer"
        DEFAULT = "DEFAULT", "Default fallback"

    link = models.ForeignKey(urlModel, on_delete=models.CASCADE, related_name="routing_rules")
    name = models.CharField(max_length=120)
    condition_type = models.CharField(max_length=24, choices=ConditionType.choices)
    match_value = models.CharField(
        max_length=500,
        blank=True,
        help_text="Value to match. Date/time windows use start/end ISO-8601 values.",
    )
    destination_url = models.URLField(max_length=2048)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("priority", "pk")
        indexes = [models.Index(fields=("link", "is_active", "priority"))]

    def __str__(self):
        return f"{self.link.shorturl}: {self.name}"


class Experiment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        COMPLETED = "COMPLETED", "Completed"

    class AssignmentStrategy(models.TextChoices):
        DETERMINISTIC = "DETERMINISTIC", "Stable visitor assignment"
        RANDOM = "RANDOM", "Random per click"

    link = models.ForeignKey(urlModel, on_delete=models.CASCADE, related_name="experiments")
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    assignment_strategy = models.CharField(
        max_length=16,
        choices=AssignmentStrategy.choices,
        default=AssignmentStrategy.DETERMINISTIC,
    )
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_experiments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("link",),
                condition=Q(status="ACTIVE"),
                name="one_active_experiment_per_link",
            ),
            models.CheckConstraint(
                check=Q(start_at__isnull=True)
                | Q(end_at__isnull=True)
                | Q(end_at__gte=F("start_at")),
                name="experiment_end_not_before_start",
            ),
        ]

    def __str__(self):
        return self.name


class ExperimentVariant(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=80)
    destination_url = models.URLField(max_length=2048)
    weight = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)
        constraints = [
            models.UniqueConstraint(
                fields=("experiment", "name"),
                name="unique_experiment_variant_name",
            ),
            models.CheckConstraint(
                check=Q(weight__gte=1) & Q(weight__lte=100),
                name="experiment_variant_weight_range",
            ),
        ]

    @property
    def click_count(self):
        return self.click_events.count()

    @property
    def conversion_count(self):
        return self.conversions.count()

    @property
    def conversion_rate(self):
        clicks = self.click_count
        return round((self.conversion_count / clicks) * 100, 2) if clicks else 0

    def __str__(self):
        return f"{self.experiment.name}: {self.name}"


class LinkVersion(models.Model):
    link = models.ForeignKey(urlModel, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="link_versions",
    )
    snapshot = models.JSONField(default=dict)
    change_summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("link", "version_number"),
                name="unique_link_version_number",
            )
        ]

    def __str__(self):
        return f"/{self.link.shorturl} v{self.version_number}"


class ConversionEvent(models.Model):
    class EventType(models.TextChoices):
        SIGNUP = "SIGNUP", "Signup"
        PURCHASE = "PURCHASE", "Purchase"
        DOWNLOAD = "DOWNLOAD", "Download"
        FORM_SUBMISSION = "FORM_SUBMISSION", "Form submission"
        CUSTOM = "CUSTOM", "Custom"

    click = models.ForeignKey(
        ClickEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversions",
    )
    link = models.ForeignKey(
        urlModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversions",
    )
    campaign = models.ForeignKey(
        Campaign,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversions",
    )
    experiment_variant = models.ForeignKey(
        ExperimentVariant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversions",
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    custom_name = models.CharField(max_length=100, blank=True)
    monetary_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    deduplication_key = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("link", "event_type", "-created_at"))]
        constraints = [
            models.UniqueConstraint(
                fields=("link", "deduplication_key"),
                condition=~Q(deduplication_key=""),
                name="unique_link_conversion_deduplication_key",
            ),
            models.CheckConstraint(
                check=Q(monetary_value__isnull=True) | Q(monetary_value__gte=0),
                name="conversion_value_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} · {self.created_at:%Y-%m-%d %H:%M:%S}"


class ApprovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="approval_requests")
    link = models.ForeignKey(
        urlModel,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    campaign = models.ForeignKey(
        Campaign,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_approvals",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_approvals",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    requester_comment = models.TextField(blank=True)
    reviewer_comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at",)
        constraints = [
            models.CheckConstraint(
                check=(Q(link__isnull=False, campaign__isnull=True) | Q(link__isnull=True, campaign__isnull=False)),
                name="approval_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=("link",),
                condition=Q(status="PENDING", link__isnull=False),
                name="one_pending_approval_per_link",
            ),
            models.UniqueConstraint(
                fields=("campaign",),
                condition=Q(status="PENDING", campaign__isnull=False),
                name="one_pending_approval_per_campaign",
            ),
        ]

    @property
    def target(self):
        return self.link or self.campaign

    def __str__(self):
        return f"{self.get_status_display()}: {self.target}"


class AbuseReport(models.Model):
    class Reason(models.TextChoices):
        PHISHING = "PHISHING", "Phishing"
        MALWARE = "MALWARE", "Malware"
        SPAM = "SPAM", "Spam"
        IMPERSONATION = "IMPERSONATION", "Impersonation"
        ILLEGAL_CONTENT = "ILLEGAL_CONTENT", "Illegal content"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        ACTIONED = "ACTIONED", "Actioned"
        DISMISSED = "DISMISSED", "Dismissed"

    link = models.ForeignKey(urlModel, on_delete=models.CASCADE, related_name="abuse_reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_abuse_reports",
    )
    reporter_email = models.EmailField(blank=True)
    reason = models.CharField(max_length=24, choices=Reason.choices)
    details = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_abuse_reports",
    )
    resolution = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "-created_at"))]

    def __str__(self):
        return f"{self.get_reason_display()} report for /{self.link.shorturl}"


class ApiCredential(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="api_credentials",
    )
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=20, unique=True, db_index=True)
    key_hash = models.CharField(max_length=255, editable=False)
    scopes = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_api_credentials",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("workspace", "revoked_at"))]

    @property
    def is_active(self):
        now = timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)

    def __str__(self):
        return f"{self.name} ({self.prefix})"


class WebhookEndpoint(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
    )
    name = models.CharField(max_length=120)
    endpoint_url = models.URLField(max_length=2048)
    secret_seed = models.CharField(max_length=128, editable=False)
    secret_prefix = models.CharField(max_length=16, editable=False)
    subscribed_events = models.JSONField(default=list)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_webhooks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")
        indexes = [models.Index(fields=("workspace", "is_active"))]

    def __str__(self):
        return self.name


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        RETRYING = "RETRYING", "Retrying"

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_type = models.CharField(max_length=48, db_index=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.CharField(max_length=1000, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "next_retry_at"))]

    def __str__(self):
        return f"{self.event_type} → {self.endpoint.name}"


class AnalyticsAnomaly(models.Model):
    class AnomalyType(models.TextChoices):
        TRAFFIC_SPIKE = "TRAFFIC_SPIKE", "Traffic spike"
        TRAFFIC_DROP = "TRAFFIC_DROP", "Traffic drop"
        BOT_SPIKE = "BOT_SPIKE", "Bot spike"
        REFERRER_SHIFT = "REFERRER_SHIFT", "Abnormal referrer distribution"
        GEO_SHIFT = "GEO_SHIFT", "Unusual geography"
        CONVERSION_DROP = "CONVERSION_DROP", "Conversion drop"

    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="analytics_anomalies",
    )
    link = models.ForeignKey(
        urlModel,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="analytics_anomalies",
    )
    campaign = models.ForeignKey(
        Campaign,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="analytics_anomalies",
    )
    anomaly_type = models.CharField(max_length=24, choices=AnomalyType.choices, db_index=True)
    severity = models.CharField(max_length=12, choices=Severity.choices, db_index=True)
    baseline_value = models.FloatField()
    observed_value = models.FloatField()
    explanation = models.CharField(max_length=500)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-detected_at",)
        indexes = [models.Index(fields=("workspace", "-detected_at"))]

    def __str__(self):
        return f"{self.get_anomaly_type_display()} · {self.workspace}"


class NotificationDelivery(models.Model):
    class Status(models.TextChoices):
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    workspace = models.ForeignKey(
        Workspace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_deliveries",
    )
    event_type = models.CharField(max_length=48, db_index=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=8, choices=Status.choices)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.event_type} → {self.recipient}"


class AuditLog(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("workspace", "-created_at"))]

    def __str__(self):
        return f"{self.action} · {self.created_at:%Y-%m-%d %H:%M:%S}"
