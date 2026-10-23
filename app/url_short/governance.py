from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ApprovalRequest, Campaign, urlModel


@transaction.atomic
def submit_link_for_approval(link, requester, comment=""):
    if link.approval_status == urlModel.ApprovalStatus.APPROVED:
        raise ValidationError("This link is already approved.")
    existing = ApprovalRequest.objects.filter(
        link=link,
        status=ApprovalRequest.Status.PENDING,
    ).first()
    if existing:
        return existing, False
    approval = ApprovalRequest.objects.create(
        workspace=link.workspace,
        link=link,
        requester=requester,
        requester_comment=comment.strip()[:2000],
    )
    link.approval_status = urlModel.ApprovalStatus.PENDING_APPROVAL
    link.save(update_fields=("approval_status", "updated_at"))
    return approval, True


@transaction.atomic
def submit_campaign_for_approval(campaign, requester, comment=""):
    existing = ApprovalRequest.objects.filter(
        campaign=campaign,
        status=ApprovalRequest.Status.PENDING,
    ).first()
    if existing:
        return existing, False
    approval = ApprovalRequest.objects.create(
        workspace=campaign.workspace,
        campaign=campaign,
        requester=requester,
        requester_comment=comment.strip()[:2000],
    )
    campaign.status = Campaign.Status.DRAFT
    campaign.save(update_fields=("status", "updated_at"))
    return approval, True


@transaction.atomic
def review_approval(approval, reviewer, *, approve, comment=""):
    if approval.status != ApprovalRequest.Status.PENDING:
        raise ValidationError("This approval request has already been reviewed.")
    approval.status = ApprovalRequest.Status.APPROVED if approve else ApprovalRequest.Status.REJECTED
    approval.reviewer = reviewer
    approval.reviewer_comment = comment.strip()[:2000]
    approval.reviewed_at = timezone.now()
    approval.save(
        update_fields=("status", "reviewer", "reviewer_comment", "reviewed_at")
    )
    if approval.link_id:
        approval.link.approval_status = (
            urlModel.ApprovalStatus.APPROVED if approve else urlModel.ApprovalStatus.REJECTED
        )
        approval.link.save(update_fields=("approval_status", "updated_at"))
    elif approval.campaign_id:
        approval.campaign.status = Campaign.Status.ACTIVE if approve else Campaign.Status.DRAFT
        approval.campaign.save(update_fields=("status", "updated_at"))
    return approval
