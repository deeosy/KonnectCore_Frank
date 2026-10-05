"""Collection settlement (allocation) rules. See docs/architecture.md, Finance."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.collections.models import CollectionRecord
from apps.farms.models import Crop
from apps.members.models import Member
from apps.organisations.models import Organisation, OrganisationMembership

from .models import FinancialRecord, PaymentAllocation

User = get_user_model()
D = Decimal


class AllocationRuleTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Alloc Org", slug="alloc-org")
        self.other_org = Organisation.objects.create(name="Alloc Other", slug="alloc-other")
        self.user = User.objects.create_user(email="mgr@alloc.test", password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=self.user, role="manager")
        self.other_user = User.objects.create_user(email="mgr@alloc-other.test", password="x")
        OrganisationMembership.objects.create(organisation=self.other_org, user=self.other_user, role="manager")
        self.member = self.make_member(self.org, self.user, "A1")
        self.member2 = self.make_member(self.org, self.user, "A2")
        self.crop = Crop.objects.create(organisation=self.org, name="Maize")
        # 100 x 5.00 = 500.00 and 60 x 5.00 = 300.00
        self.c1 = self.collection(self.member, "100")
        self.c2 = self.collection(self.member, "60")
        # Scheduled 1,000.00, actually paid 400.00
        self.payment = self.pay(D("1000.00"), D("400.00"), FinancialRecord.Status.PART_PAID)

    def make_member(self, org, user, number):
        return Member.objects.create(organisation=org, created_by=user, updated_by=user, membership_number=number, first_name="F" + number, last_name="L")

    def collection(self, member, quantity, org=None, user=None, crop=None):
        return CollectionRecord.objects.create(
            organisation=org or self.org, member=member, crop=crop or self.crop, quantity=D(quantity),
            quantity_unit="kg", collection_date=date(2026, 9, 1), collection_location="Point",
            price_per_unit=D("5.00"), recorded_by=user or self.user,
        )

    def pay(self, amount, paid, status, purpose=FinancialRecord.Purpose.COLLECTIONS, member=None):
        return FinancialRecord.objects.create(
            organisation=self.org, record_type=FinancialRecord.Type.MEMBER_PAYMENT, member=member or self.member,
            amount=amount, paid_amount=paid, payment_method="cash", status=status, payment_date=date(2026, 9, 5),
            recorded_by=self.user, purpose=purpose,
        )

    def alloc(self, collection, amount, payment=None, save=True):
        a = PaymentAllocation(organisation=self.org, payment=payment or self.payment, collection=collection, amount=D(amount), created_by=self.user)
        a.full_clean()
        if save:
            a.save()
        return a

    def errors(self, obj):
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        return ctx.exception.message_dict

    # Paid vs scheduled
    def test_only_paid_amount_can_be_allocated_not_scheduled_amount(self):
        self.alloc(self.c1, "300.00")
        extra = PaymentAllocation(organisation=self.org, payment=self.payment, collection=self.c2, amount=D("200.00"), created_by=self.user)
        self.assertIn("amount", self.errors(extra))  # only 100.00 of the 400.00 paid is left
        self.alloc(self.c2, "100.00")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.allocated_amount, D("400.00"))
        self.assertEqual(self.payment.unallocated_amount, D("0.00"))
        self.assertEqual(self.c1.allocated_amount + self.c2.allocated_amount, D("400.00"))  # never 1,000

    def test_partial_distribution_is_explicit_and_balance_tracked(self):
        self.alloc(self.c1, "250.00")
        self.assertEqual(self.payment.unallocated_amount, D("150.00"))
        self.assertEqual(self.c1.allocated_amount, D("250.00"))
        self.assertEqual(self.c1.unallocated_value, D("250.00"))
        self.assertEqual(self.c2.allocated_amount, D("0.00"))  # nothing auto-split

    def test_collection_value_limit_across_payments(self):
        second = self.pay(D("400.00"), D("400.00"), FinancialRecord.Status.PAID)
        self.alloc(self.c1, "400.00")
        over = PaymentAllocation(organisation=self.org, payment=second, collection=self.c1, amount=D("150.00"), created_by=self.user)
        self.assertIn("amount", self.errors(over))  # only 100.00 of the 500.00 value left
        self.alloc(self.c1, "100.00", payment=second)
        self.assertEqual(self.c1.allocated_amount, D("500.00"))

    # Ownership and state
    def test_collection_must_belong_to_same_member(self):
        other_member_collection = self.collection(self.member2, "10")
        bad = PaymentAllocation(organisation=self.org, payment=self.payment, collection=other_member_collection, amount=D("10.00"), created_by=self.user)
        self.assertIn("collection", self.errors(bad))

    def test_collection_must_belong_to_same_organisation(self):
        foreign_member = self.make_member(self.other_org, self.other_user, "X1")
        foreign_crop = Crop.objects.create(organisation=self.other_org, name="Maize")
        foreign = self.collection(foreign_member, "10", org=self.other_org, user=self.other_user, crop=foreign_crop)
        bad = PaymentAllocation(organisation=self.org, payment=self.payment, collection=foreign, amount=D("10.00"), created_by=self.user)
        self.assertIn("collection", self.errors(bad))

    def test_new_allocation_to_voided_collection_rejected(self):
        self.c1.voided_at = timezone.now()
        self.c1.voided_by = self.user
        self.c1.void_reason = "Duplicate"
        self.c1.save()
        bad = PaymentAllocation(organisation=self.org, payment=self.payment, collection=self.c1, amount=D("10.00"), created_by=self.user)
        self.assertIn("collection", self.errors(bad))

    def test_only_for_collections_member_payments_allocate(self):
        other = self.pay(D("50.00"), D("50.00"), FinancialRecord.Status.PAID, purpose=FinancialRecord.Purpose.OTHER)
        other.purpose_description = "Transport refund"
        bad = PaymentAllocation(organisation=self.org, payment=other, collection=self.c1, amount=D("10.00"), created_by=self.user)
        self.assertIn("payment", self.errors(bad))
        unresolved = self.pay(D("50.00"), D("50.00"), FinancialRecord.Status.PAID, purpose="")
        self.assertTrue(unresolved.is_unresolved_purpose)
        bad2 = PaymentAllocation(organisation=self.org, payment=unresolved, collection=self.c1, amount=D("10.00"), created_by=self.user)
        self.assertIn("payment", self.errors(bad2))

    def test_purpose_rules(self):
        other = FinancialRecord(organisation=self.org, record_type=FinancialRecord.Type.MEMBER_PAYMENT, member=self.member, amount=D("10"), paid_amount=D("10"), payment_method="cash", status="paid", payment_date=date(2026, 9, 5), recorded_by=self.user, purpose=FinancialRecord.Purpose.OTHER)
        self.assertIn("purpose_description", self.errors(other))
        due = FinancialRecord(organisation=self.org, record_type=FinancialRecord.Type.DUE, member=self.member, amount=D("10"), paid_amount=D("0"), payment_method="cash", status="pending", payment_date=date(2026, 9, 5), recorded_by=self.user, purpose=FinancialRecord.Purpose.COLLECTIONS)
        self.assertIn("purpose", self.errors(due))

    # Revalidation on edit
    def test_payment_paid_amount_cannot_drop_below_allocated(self):
        self.alloc(self.c1, "300.00")
        self.payment.paid_amount = D("200.00")
        self.assertIn("paid_amount", self.errors(self.payment))
        self.payment.refresh_from_db()
        self.payment.purpose = FinancialRecord.Purpose.OTHER
        self.payment.purpose_description = "Changed"
        self.assertIn("purpose", self.errors(self.payment))

    def test_collection_value_cannot_drop_below_allocated(self):
        self.alloc(self.c1, "300.00")
        self.c1.quantity = D("50")  # value would be 250.00
        self.assertIn("quantity", self.errors(self.c1))
        self.c1.quantity = D("60")  # 300.00 is still fine
        self.c1.full_clean()

    def test_editing_allocation_revalidates_limits(self):
        a = self.alloc(self.c1, "300.00")
        a.amount = D("450.00")  # payment only has 400.00 paid
        self.assertIn("amount", self.errors(a))
        a.amount = D("400.00")
        a.full_clean()

    # Cancelled payments, corrections, uniqueness
    def test_cancelled_payment_allocations_stop_counting(self):
        self.alloc(self.c1, "300.00")
        FinancialRecord.objects.filter(pk=self.payment.pk).update(status=FinancialRecord.Status.CANCELLED)
        self.assertEqual(self.c1.allocated_amount, D("0.00"))
        self.assertEqual(PaymentAllocation.objects.filter(collection=self.c1).count(), 1)  # history kept

    def test_removal_requires_reason_and_frees_amount(self):
        a = self.alloc(self.c1, "300.00")
        a.removed_at = timezone.now()
        a.removed_by = self.user
        self.assertIn("removal_reason", self.errors(a))
        a.removal_reason = "Allocated to the wrong collection"
        a.full_clean()
        a.save()
        self.assertEqual(self.c1.allocated_amount, D("0.00"))
        self.assertEqual(self.payment.allocated_amount, D("0.00"))
        self.alloc(self.c2, "300.00")  # moved
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.payment).count(), 2)

    def test_one_active_allocation_per_payment_and_collection(self):
        self.alloc(self.c1, "100.00")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAllocation.objects.create(organisation=self.org, payment=self.payment, collection=self.c1, amount=D("50.00"), created_by=self.user)
