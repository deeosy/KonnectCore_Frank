"""Save a payment and its collection allocations together.

Rules: docs/architecture.md, Finance > Collection settlement.

Order inside one transaction (a failure rolls back everything):
1. Lock the payment (edits) and every affected collection row.
2. Mark allocations whose amount changed or was cleared as removed, with the reason.
3. Save the payment (create uses one-time submission keys; an exact repeat returns the
   original payment and adds nothing).
4. Create the new or changed allocations; each is fully validated against the saved
   payment's paid_amount and the collection's value.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.collections.models import CollectionRecord
from apps.core.submissions import save_once

from .models import FinancialRecord, PaymentAllocation

ZERO = Decimal("0.00")


def allocatable_collections(organisation, member, payment=None):
    """The member's non-voided collections, plus any the payment already allocates to."""
    queryset = CollectionRecord.objects.for_organisation(organisation).filter(member=member)
    if payment is not None and payment.pk:
        active = payment.allocations.filter(removed_at__isnull=True).values("collection_id")
        queryset = queryset.filter(Q(voided_at__isnull=True) | Q(pk__in=active))
    else:
        queryset = queryset.filter(voided_at__isnull=True)
    return queryset.select_related("crop").order_by("-collection_date", "-created_at")


def active_allocations(payment):
    """{collection_id: allocation} for the payment's active allocations."""
    if payment is None or not payment.pk:
        return {}
    return {a.collection_id: a for a in payment.allocations.filter(removed_at__isnull=True)}


def _lock_collections(organisation, collection_ids):
    if collection_ids:
        list(CollectionRecord.objects.select_for_update().filter(organisation=organisation, pk__in=list(collection_ids)))


def save_payment_with_allocations(form, *, actor):
    """Return (payment, created). Raises ValidationError or SubmissionConflict; nothing is saved on error."""
    desired = form.allocation_amounts()
    reason = form.get_allocation_change_reason()
    organisation = form.organisation
    editing = not form.instance._state.adding
    with transaction.atomic():
        previous = {}
        if editing:
            FinancialRecord.objects.select_for_update().get(pk=form.instance.pk, organisation=organisation)
            current = active_allocations(form.instance)
            previous = {cid: a.amount for cid, a in current.items()}
            _lock_collections(organisation, set(desired) | set(previous))
            now = timezone.now()
            for cid, allocation in current.items():
                if desired.get(cid, ZERO) != allocation.amount:
                    allocation.removed_at = now
                    allocation.removed_by = actor
                    allocation.removal_reason = reason
                    allocation.full_clean()
                    allocation.save(update_fields=["removed_at", "removed_by", "removal_reason"])
            payment, created = form.save(), False
        else:
            _lock_collections(organisation, set(desired))
            payment, created = save_once(form, organisation=organisation, actor=actor)
            if not created:
                return payment, False
        for cid, amount in desired.items():
            if amount <= 0 or previous.get(cid) == amount:
                continue
            allocation = PaymentAllocation(
                organisation_id=payment.organisation_id, payment=payment,
                collection_id=cid, amount=amount, created_by=actor,
            )
            allocation.full_clean()
            allocation.save()
    return payment, created
