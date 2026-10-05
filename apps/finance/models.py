import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.members.models import Member
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
        if errors: raise ValidationError(errors)
    @property
    def outstanding_amount(self):
        if self.status == self.Status.CANCELLED: return Decimal("0.00")
        return self.amount - self.paid_amount
    def __str__(self): return f"{self.get_record_type_display()} - {self.amount}"