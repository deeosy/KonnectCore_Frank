import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.members.models import Member
from apps.collections.models import CollectionRecord
from apps.organisations.models import OrganisationMembership, OrganisationOwnedModel

class FinancialRecord(OrganisationOwnedModel):
    class Type(models.TextChoices):
        MEMBER_PAYMENT = "member_payment", "Payment to member"
        DUE = "due", "Membership due"
        CONTRIBUTION = "contribution", "Contribution"
        SAVING = "saving", "Savings"
        EXPENSE = "expense", "Organisation expense"
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        OTHER = "other", "Other"
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PART_PAID = "part_paid", "Part-paid"
        CANCELLED = "cancelled", "Cancelled"
    class Purpose(models.TextChoices):
        COLLECTIONS = "collections", "For collections"
        OTHER = "other", "Other"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record_type = models.CharField(max_length=20, choices=Type.choices)
    member = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT, related_name="financial_records")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payment_date = models.DateField()
    reference_number = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    # Payment to member only. Blank = purpose not recorded (records created before allocations; unresolved).
    purpose = models.CharField(max_length=16, choices=Purpose.choices, blank=True)
    purpose_description = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="financial_records_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # One-time form submission key (see apps/core/submissions.py); prevents duplicate records.
    submission_key = models.UUIDField(null=True, blank=True, editable=False)
    submission_fingerprint = models.CharField(max_length=64, blank=True, editable=False)
    class Meta:
        ordering = ["-payment_date", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="finance_amount_positive"),
            models.CheckConstraint(condition=models.Q(paid_amount__gte=0), name="finance_paid_nonnegative"),
            models.CheckConstraint(condition=models.Q(paid_amount__lte=models.F("amount")), name="finance_paid_lte_amount"),
            models.UniqueConstraint(
                fields=["organisation", "submission_key"],
                condition=models.Q(submission_key__isnull=False),
                name="unique_finance_submission_key",
            ),
        ]
        indexes = [models.Index(fields=["organisation", "payment_date"]), models.Index(fields=["organisation", "record_type"]), models.Index(fields=["organisation", "status"]), models.Index(fields=["organisation", "member"])]
    def clean(self):
        errors = {}
        self.reference_number = self.reference_number.strip()
        if self.record_type == self.Type.EXPENSE and self.member_id:
            errors["member"] = "Organisation expenses cannot be assigned to a member."
        if self.record_type != self.Type.EXPENSE and not self.member_id:
            errors["member"] = "Select a member for this record type."
        if self.member_id and self.organisation_id and self.member.organisation_id != self.organisation_id:
            errors["member"] = "Member must belong to the same organisation."
        if self.amount is not None and self.amount <= 0: errors["amount"] = "Amount must be greater than zero."
        if self.paid_amount is not None and self.paid_amount < 0: errors["paid_amount"] = "Paid amount cannot be negative."
        if self.amount is not None and self.paid_amount is not None and self.paid_amount > self.amount: errors["paid_amount"] = "Paid amount cannot exceed amount."
        if self.status == self.Status.PAID and self.amount is not None and self.paid_amount != self.amount: errors["paid_amount"] = "Paid records must have the full amount paid."
        if self.status == self.Status.PENDING and self.paid_amount: errors["paid_amount"] = "Pending records cannot have a paid amount."
        if self.status == self.Status.PART_PAID and (not self.paid_amount or self.paid_amount >= self.amount): errors["paid_amount"] = "Part-paid records require a paid amount below the total."
        if self.recorded_by_id and self.organisation_id and not OrganisationMembership.objects.filter(organisation_id=self.organisation_id, user_id=self.recorded_by_id).exists(): errors["recorded_by"] = "Recorder must belong to the same organisation."
        self.purpose_description = (self.purpose_description or "").strip()
        if self.record_type != self.Type.MEMBER_PAYMENT and self.purpose:
            errors["purpose"] = "Only payments to members have a purpose."
        if self.purpose == self.Purpose.OTHER and not self.purpose_description:
            errors["purpose_description"] = "Describe what this payment is for."
        if self.pk and not self._state.adding and self.paid_amount is not None and self.status != self.Status.CANCELLED:
            # Forms set _pending_allocated to the total being submitted; otherwise use saved allocations.
            pending = getattr(self, "_pending_allocated", None)
            allocated = pending if pending is not None else self.allocated_amount
            if self.paid_amount < allocated:
                errors["paid_amount"] = f"Paid amount cannot be less than the {allocated} already allocated to collections. Move or remove allocations first."
            if self.purpose != self.Purpose.COLLECTIONS and allocated:
                errors["purpose"] = "This payment has collection allocations. Remove them before changing its purpose."
        if errors: raise ValidationError(errors)
    @property
    def outstanding_amount(self):
        if self.status == self.Status.CANCELLED: return Decimal("0.00")
        return self.amount - self.paid_amount
    @property
    def is_unresolved_purpose(self):
        return self.record_type == self.Type.MEMBER_PAYMENT and not self.purpose
    @property
    def allocated_amount(self):
        """Money actually paid that is allocated to collections (active allocations only)."""
        if not self.pk: return Decimal("0.00")
        total = self.allocations.filter(removed_at__isnull=True).aggregate(total=models.Sum("amount"))["total"]
        return (total or Decimal("0.00")).quantize(Decimal("0.01"))
    @property
    def unallocated_amount(self):
        """Paid money on a For-collections payment not yet allocated to any collection."""
        if self.purpose != self.Purpose.COLLECTIONS: return Decimal("0.00")
        return self.paid_amount - self.allocated_amount
    def __str__(self): return f"{self.get_record_type_display()} - {self.amount}"


class PaymentAllocation(OrganisationOwnedModel):
    """A portion of a payment's paid_amount settled against one collection.

    Allocations are never deleted: corrections set removed_at/removed_by/removal_reason,
    so the correction history is preserved. Only active (removed_at is null) allocations count.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(FinancialRecord, on_delete=models.PROTECT, related_name="allocations")
    collection = models.ForeignKey(CollectionRecord, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_allocations_created")
    created_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="payment_allocations_removed")
    removal_reason = models.TextField(blank=True)
    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="allocation_amount_positive"),
            models.UniqueConstraint(fields=["payment", "collection"], condition=models.Q(removed_at__isnull=True), name="unique_active_payment_collection_allocation"),
        ]
        indexes = [models.Index(fields=["organisation", "collection"]), models.Index(fields=["organisation", "payment"])]
    @property
    def is_active(self):
        return self.removed_at is None
    def clean(self):
        errors = {}
        payment = self.payment if self.payment_id else None
        collection = self.collection if self.collection_id else None
        if payment is not None:
            if payment.organisation_id != self.organisation_id:
                errors["payment"] = "Payment must belong to the same organisation."
            elif payment.record_type != FinancialRecord.Type.MEMBER_PAYMENT:
                errors["payment"] = "Only payments to members can be allocated to collections."
            elif payment.purpose != FinancialRecord.Purpose.COLLECTIONS:
                errors["payment"] = "Set the payment purpose to For collections before allocating it."
        if collection is not None:
            if collection.organisation_id != self.organisation_id:
                errors["collection"] = "Collection must belong to the same organisation."
            elif payment is not None and collection.member_id != payment.member_id:
                errors["collection"] = "Collection must belong to the same member as the payment."
            elif self.is_active and self._state.adding and getattr(collection, "voided_at", None):
                errors["collection"] = "This collection is voided; payments cannot be allocated to it."
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Allocated amount must be greater than zero."
        if not errors and self.is_active and payment is not None and collection is not None and self.amount is not None:
            others = PaymentAllocation.objects.filter(removed_at__isnull=True).exclude(pk=self.pk)
            paid_used = others.filter(payment=payment).aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
            if paid_used + self.amount > payment.paid_amount:
                errors["amount"] = f"Only {payment.paid_amount - paid_used} of this payment's paid amount is unallocated."
            if payment.status != FinancialRecord.Status.CANCELLED:
                value_used = others.filter(collection=collection).exclude(payment__status=FinancialRecord.Status.CANCELLED).aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
                if value_used + self.amount > collection.total_value:
                    errors["amount"] = f"Only {collection.total_value - value_used} of this collection's value is unallocated."
        if self.removed_at and not (self.removal_reason or "").strip():
            errors["removal_reason"] = "Give a reason for removing or moving this allocation."
        if errors: raise ValidationError(errors)
    def __str__(self): return f"{self.amount} of {self.payment_id} to {self.collection_id}"