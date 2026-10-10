import uuid
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.core.submissions import FIELD_NAME, add_submission_key
from apps.members.models import Member

from .allocations import active_allocations, allocatable_collections
from .models import FinancialRecord

ZERO = Decimal("0.00")
ALLOC_PREFIX = "alloc_"


class PlaceholderSelect(forms.Select):
    """Select whose blank option is a disabled placeholder (shown, but not pickable from the list)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value in ("", None):
            option["attrs"]["disabled"] = True
        return option


class FinancialRecordForm(forms.ModelForm):
    """Payments, dues and expenses. Collection allocation rules: docs/architecture.md, Finance."""

    allocation_change_reason = forms.CharField(
        required=False,
        label="Reason for changing allocations",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when you change or remove an existing allocation. The previous allocation is kept in the history.",
    )

    class Meta:
        model = FinancialRecord
        fields = ["record_type", "member", "amount", "paid_amount", "payment_method", "status", "payment_date", "purpose", "purpose_description", "reference_number", "notes"]
        widgets = {"payment_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}
        labels = {
            "amount": "Amount owed or scheduled",
            "paid_amount": "Amount actually paid",
            "purpose": "Purpose (payments to members only)",
            "purpose_description": "What is this payment for?",
        }
        help_texts = {
            "paid_amount": "Money that has actually been paid. Only this money can be allocated to collections.",
            "purpose_description": "Required when the purpose is Other, for example an advance or transport refund.",
        }

    def __init__(self, *args, organisation, recorded_by, **kwargs):
        self.organisation = organisation
        self.recorded_by = recorded_by
        super().__init__(*args, **kwargs)
        self.instance.organisation = organisation
        adding = self.instance._state.adding
        if adding:
            self.instance.recorded_by = recorded_by
            del self.fields["allocation_change_reason"]
        self.fields["member"].queryset = Member.objects.for_organisation(organisation)
        self.fields["purpose"].required = False
        self._apply_choice_prompts()
        self.fields["paid_amount"].required = False
        if adding and not self.is_bound and not self.initial.get("paid_amount"):
            # Start empty so a misleading 0 is not left unchanged; a blank value still saves as 0 (UI review item 4).
            self.initial["paid_amount"] = None
        self._previous = {} if adding else active_allocations(self.instance)
        # An exact repeat of an already-saved create form (double click) must validate like the
        # original, so the original payment's allocations are not counted against availability.
        self.replay_of = self._find_replay() if adding else None
        owner = self.replay_of if adding else self.instance
        own_allocations = active_allocations(owner) if owner is not None else {}
        owner_counts = owner is None or owner.status != FinancialRecord.Status.CANCELLED
        self._desired = {}
        self.allocation_collections = {}
        member = self._resolve_member()
        if member is not None:
            for collection in allocatable_collections(organisation, member, owner):
                name = f"{ALLOC_PREFIX}{collection.pk}"
                previous = self._previous.get(collection.pk)
                owned = own_allocations.get(collection.pk)
                own = owned.amount if owned is not None and owner_counts else ZERO
                others = collection.allocated_amount - own
                available = collection.total_value - others
                self.allocation_collections[name] = (collection, available)
                self.fields[name] = forms.DecimalField(
                    required=False, min_value=ZERO, max_digits=16, decimal_places=2,
                    label=f"{collection.collection_date:%Y-%m-%d} - {collection.crop.display_name} - {collection.quantity} {collection.get_quantity_unit_display()}",
                    help_text=f"Value {collection.total_value}. Already allocated from other payments {others}. Available {available}.",
                    initial=previous.amount if previous is not None else None,
                )
        add_submission_key(self)

    def _resolve_member(self):
        return self._resolve_member_value()

    def _find_replay(self):
        """The saved payment whose submission key this bound create form reuses, if any."""
        if not self.is_bound:
            return None
        raw = self.data.get(self.add_prefix(FIELD_NAME))
        try:
            key = uuid.UUID(str(raw))
        except (TypeError, ValueError, AttributeError):
            return None
        return FinancialRecord.objects.for_organisation(self.organisation).filter(submission_key=key).first()

    def _resolve_member_value(self):
        value = self.data.get(self.add_prefix("member")) if self.is_bound else None
        if not value:
            value = self.initial.get("member") or self.instance.member_id
        value = getattr(value, "pk", value)
        if not value:
            return None
        try:
            return self.fields["member"].queryset.filter(pk=value).first()
        except (ValueError, ValidationError):
            return None

    def allocation_fields(self):
        return [self[name] for name in self.allocation_collections]

    PROMPTS = {
        "member": "Choose a member",
        "record_type": "Choose a record type",
        "payment_method": "Choose a payment method",
        "purpose": "Choose a purpose",
    }

    def _apply_choice_prompts(self):
        """Replace Django's '---------' blank choices with plain prompts.

        On required dropdowns the prompt is a disabled placeholder, so it cannot be picked
        from the list. Optional dropdowns keep a selectable blank so they can be cleared.
        """
        for name, prompt in self.PROMPTS.items():
            field = self.fields.get(name)
            if field is None:
                continue
            if hasattr(field, "empty_label"):
                if field.empty_label is not None:
                    field.empty_label = prompt
            else:
                field.choices = [("", prompt) if value == "" else (value, label) for value, label in field.choices]
            if field.required:
                widget = PlaceholderSelect(attrs=field.widget.attrs)
                widget.choices = field.widget.choices
                widget.is_required = True
                field.widget = widget

    def clean_paid_amount(self):
        value = self.cleaned_data.get("paid_amount")
        return ZERO if value is None else value

    def clean(self):
        data = super().clean()
        record_type = data.get("record_type")
        purpose = data.get("purpose") or ""
        adding = self.instance._state.adding
        if record_type == FinancialRecord.Type.MEMBER_PAYMENT:
            if not purpose and (adding or self.instance.purpose):
                self.add_error("purpose", "Choose what this payment is for: collections or another purpose.")
        else:
            data["purpose"] = ""
            data["purpose_description"] = ""
            purpose = ""
        desired = {}
        if record_type == FinancialRecord.Type.MEMBER_PAYMENT and purpose == FinancialRecord.Purpose.COLLECTIONS:
            for name, (collection, available) in self.allocation_collections.items():
                amount = data.get(name)
                if not amount:
                    continue
                desired[collection.pk] = amount
                if amount > available:
                    self.add_error(name, f"Only {available} of this collection's value is available.")
            paid = data.get("paid_amount") or ZERO
            total = sum(desired.values(), ZERO)
            if total > paid:
                self.add_error(None, f"Allocations total {total}, but only {paid} has actually been paid. Allocate only money actually paid.")
            if paid > 0 and not desired:
                if self.allocation_collections:
                    self.add_error(None, "Enter how much of the amount actually paid settles each collection.")
                else:
                    self.add_error("member", "This member has no collections to allocate to. Choose another purpose or record the collection first.")
        changed = any(desired.get(cid) != allocation.amount for cid, allocation in self._previous.items())
        if changed and not (data.get("allocation_change_reason") or "").strip():
            self.add_error("allocation_change_reason", "Give a reason for changing or removing an existing allocation.")
        self._desired = desired
        # Lets the model check paid_amount against the allocations being submitted, not the old ones.
        self.instance._pending_allocated = sum(desired.values(), ZERO)
        return data

    def allocation_amounts(self):
        return dict(self._desired)

    def get_allocation_change_reason(self):
        return (self.cleaned_data.get("allocation_change_reason") or "").strip()

    def save(self, commit=True):
        item = super().save(commit=False)
        item.organisation = self.organisation
        if item._state.adding:
            item.recorded_by = self.recorded_by
        item.full_clean()
        if commit:
            item.save()
        return item
