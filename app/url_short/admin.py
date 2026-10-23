from django.contrib import admin

from .models import (
    AuditLog,
    AbuseReport,
    ApprovalRequest,
    ApiCredential,
    AnalyticsAnomaly,
    Campaign,
    ClickEvent,
    CustomDomain,
    ConversionEvent,
    Experiment,
    ExperimentVariant,
    LinkVersion,
    NotificationDelivery,
    RedirectRule,
    Workspace,
    WorkspaceMembership,
    WebhookDelivery,
    WebhookEndpoint,
    urlModel,
)


admin.site.site_header = "OrbitLink administration"
admin.site.site_title = "OrbitLink Admin"
admin.site.index_title = "Platform control center"
admin.site.site_url = "/"
admin.site.enable_nav_sidebar = True


class WorkspaceMembershipInline(admin.TabularInline):
    model = WorkspaceMembership
    extra = 0


@admin.register(urlModel)
class UrlModelAdmin(admin.ModelAdmin):
    list_display = (
        "shorturl",
        "workspace",
        "campaign",
        "owner",
        "longurl",
        "count",
        "approval_status",
        "safety_status",
        "expires_at",
        "created_at",
    )
    search_fields = ("shorturl", "longurl", "owner__username", "workspace__name")
    list_filter = (
        "workspace",
        "campaign",
        "approval_status",
        "safety_status",
        "created_at",
        "expires_at",
    )


@admin.register(ClickEvent)
class ClickEventAdmin(admin.ModelAdmin):
    list_display = (
        "short_url",
        "clicked_at",
        "browser",
        "device_type",
        "referrer_source",
        "routing_rule",
        "bot_classification",
    )
    list_filter = (
        "bot_classification",
        "browser",
        "device_type",
        "operating_system",
        "referrer_source",
    )
    readonly_fields = ("short_url", "clicked_at", "ip_address", "user_agent", "referrer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug", "owner__username", "owner__email")
    inlines = (WorkspaceMembershipInline,)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "status", "start_at", "end_at", "created_by")
    list_filter = ("status", "workspace")
    search_fields = ("name", "description", "workspace__name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "workspace", "actor", "target_type", "target_id", "created_at")
    list_filter = ("action", "workspace", "created_at")
    search_fields = ("action", "actor__username", "target_type", "target_id")
    readonly_fields = (
        "workspace",
        "actor",
        "action",
        "target_type",
        "target_id",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CustomDomain)
class CustomDomainAdmin(admin.ModelAdmin):
    list_display = (
        "domain",
        "workspace",
        "verification_status",
        "is_active",
        "is_default",
        "created_at",
    )
    list_filter = ("verification_status", "is_active", "is_default")
    search_fields = ("domain", "workspace__name")
    readonly_fields = ("verification_token", "created_at", "verified_at")


@admin.register(RedirectRule)
class RedirectRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "link", "condition_type", "priority", "is_active")
    list_filter = ("condition_type", "is_active")
    search_fields = ("name", "link__shorturl", "destination_url")


@admin.register(LinkVersion)
class LinkVersionAdmin(admin.ModelAdmin):
    list_display = ("link", "version_number", "changed_by", "change_summary", "created_at")
    search_fields = ("link__shorturl", "change_summary", "changed_by__username")
    readonly_fields = ("link", "version_number", "changed_by", "snapshot", "change_summary", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ExperimentVariantInline(admin.TabularInline):
    model = ExperimentVariant
    extra = 0


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ("name", "link", "status", "assignment_strategy", "start_at", "end_at")
    list_filter = ("status", "assignment_strategy")
    search_fields = ("name", "link__shorturl")
    inlines = (ExperimentVariantInline,)


@admin.register(ConversionEvent)
class ConversionEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "link", "campaign", "experiment_variant", "monetary_value", "currency", "created_at")
    list_filter = ("event_type", "currency", "created_at")
    search_fields = ("link__shorturl", "custom_name", "deduplication_key")
    readonly_fields = (
        "click",
        "link",
        "campaign",
        "experiment_variant",
        "event_type",
        "custom_name",
        "monetary_value",
        "currency",
        "deduplication_key",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("workspace", "target", "requester", "status", "reviewer", "submitted_at")
    list_filter = ("status", "workspace", "submitted_at")
    search_fields = ("requester__username", "link__shorturl", "campaign__name")


@admin.register(AbuseReport)
class AbuseReportAdmin(admin.ModelAdmin):
    list_display = ("link", "reason", "status", "reporter", "created_at", "resolved_by")
    list_filter = ("reason", "status", "created_at")
    search_fields = ("link__shorturl", "details", "reporter_email")


@admin.register(ApiCredential)
class ApiCredentialAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "workspace", "created_by", "created_at", "last_used_at", "expires_at", "revoked_at")
    list_filter = ("workspace", "created_at", "revoked_at")
    search_fields = ("name", "prefix", "workspace__name")
    readonly_fields = ("prefix", "key_hash", "created_at", "last_used_at", "revoked_at")


class WebhookDeliveryInline(admin.TabularInline):
    model = WebhookDelivery
    extra = 0
    readonly_fields = ("event_type", "event_id", "status", "attempt_count", "response_code", "created_at")
    can_delete = False


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "endpoint_url", "is_active", "created_at")
    list_filter = ("is_active", "workspace")
    search_fields = ("name", "endpoint_url", "workspace__name")
    readonly_fields = ("secret_seed", "secret_prefix", "created_at", "updated_at")
    inlines = (WebhookDeliveryInline,)


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("event_type", "endpoint", "status", "attempt_count", "response_code", "created_at")
    list_filter = ("status", "event_type", "created_at")
    search_fields = ("event_id", "endpoint__name")
    readonly_fields = ("endpoint", "event_type", "event_id", "payload", "status", "attempt_count", "response_code", "response_body", "last_attempt_at", "next_retry_at", "delivered_at", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnalyticsAnomaly)
class AnalyticsAnomalyAdmin(admin.ModelAdmin):
    list_display = ("anomaly_type", "severity", "workspace", "link", "baseline_value", "observed_value", "detected_at")
    list_filter = ("anomaly_type", "severity", "workspace", "detected_at")
    search_fields = ("explanation", "link__shorturl", "workspace__name")
    readonly_fields = ("workspace", "link", "campaign", "anomaly_type", "severity", "baseline_value", "observed_value", "explanation", "detected_at")


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("event_type", "recipient", "workspace", "status", "created_at")
    list_filter = ("status", "event_type", "created_at")
    search_fields = ("recipient", "subject")
    readonly_fields = ("workspace", "event_type", "recipient", "subject", "status", "error", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
