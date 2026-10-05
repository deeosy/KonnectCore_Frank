"""Payment form + allocation saving through the views. Rules: docs/architecture.md, Finance."""
import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.collections.models import CollectionRecord
from apps.farms.models import Crop
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import FinancialRecord, PaymentAllocation

User = get_user_model()
D = Decimal


class PaymentAllocationViewTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Pay Org", slug="pay-org")
        self.manager = User.objects.create_user(email="mgr@pay.test", password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=self.manager, role="manager")
        self.member = Member.objects.create(organisation=self.org, created_by=self.manager, updated_by=self.manager, membership_number="P1", first_name="Pat", last_name="Pay")
        self.crop = Crop.objects.create(organisation=self.org, name="Maize")
        self.c1 = self.collection("100")  # 500.00
        self.c2 = self.collection("60")   # 300.00
        self.client.force_login(self.manager)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    def collection(self, quantity):
        record = CollectionRecord(
            organisation=self.org, member=self.member, crop=self.crop, quantity=D(quantity), quantity_unit="kg",
            collection_date=date(2026, 9, 1), collection_location="Point", price_per_unit=D("5.00"), recorded_by=self.manager,
        )
        record.total_value = record.calculate_total()
        record.save()
        return record

    def data(self, key=None, **extra):
        d = {
            "record_type": "member_payment", "member": str(self.member.pk), "amount": "1000.00", "paid_amount": "400.00",
            "payment_method": "cash", "status": "part_paid", "payment_date": "2026-09-05",
            "purpose": FinancialRecord.Purpose.COLLECTIONS, "purpose_description": "", "reference_number": "QA-PAY", "notes": "",
            "submission_key": str(key or uuid.uuid4()),
        }
        d.update(extra)
        return d

    def alloc(self, collection):
        return f"alloc_{collection.pk}"

    def active(self, payment=None):
        qs = PaymentAllocation.objects.filter(removed_at__isnull=True)
        if payment is not None:
            qs = qs.filter(payment=payment)
        return {a.collection_id: a.amount for a in qs}

    def test_partial_payment_allocates_only_paid_money(self):
        response = self.client.post(reverse("finance_create"), self.data(**{self.alloc(self.c1): "250.00", self.alloc(self.c2): "150.00"}))
        payment = FinancialRecord.objects.get()
        self.assertRedirects(response, reverse("finance_detail", args=[payment.pk]), fetch_redirect_response=False)
        self.assertEqual(self.active(payment), {self.c1.pk: D("250.00"), self.c2.pk: D("150.00")})
        self.assertEqual(payment.allocated_amount, D("400.00"))
        self.assertEqual(payment.unallocated_amount, D("0.00"))
        self.assertEqual(payment.outstanding_amount, D("600.00"))  # scheduled minus paid, unchanged by allocation

    def test_allocating_more_than_paid_saves_nothing(self):
        response = self.client.post(reverse("finance_create"), self.data(**{self.alloc(self.c1): "300.00", self.alloc(self.c2): "200.00"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "only 400.00 has actually been paid")
        self.assertEqual(FinancialRecord.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_allocation_above_collection_value_rejected(self):
        response = self.client.post(reverse("finance_create"), self.data(paid_amount="400.00", **{self.alloc(self.c2): "350.00"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinancialRecord.objects.count(), 0)

    def test_partly_allocated_payment_shows_unallocated_balance(self):
        self.client.post(reverse("finance_create"), self.data(**{self.alloc(self.c1): "250.00"}))
        payment = FinancialRecord.objects.get()
        self.assertEqual(payment.unallocated_amount, D("150.00"))
        detail = self.client.get(reverse("finance_detail", args=[payment.pk]))
        self.assertContains(detail, "Unallocated paid balance")
        self.assertContains(detail, "150.00 of the money actually paid is not yet allocated")

    def test_paid_collection_payment_needs_an_allocation(self):
        response = self.client.post(reverse("finance_create"), self.data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinancialRecord.objects.count(), 0)

    def test_pending_collection_payment_needs_no_allocation(self):
        self.client.post(reverse("finance_create"), self.data(paid_amount="0.00", status="pending"))
        self.assertEqual(FinancialRecord.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_purpose_required_and_other_needs_description(self):
        self.client.post(reverse("finance_create"), self.data(purpose=""))
        self.assertEqual(FinancialRecord.objects.count(), 0)
        self.client.post(reverse("finance_create"), self.data(purpose=FinancialRecord.Purpose.OTHER))
        self.assertEqual(FinancialRecord.objects.count(), 0)
        self.client.post(reverse("finance_create"), self.data(purpose=FinancialRecord.Purpose.OTHER, purpose_description="Transport refund"))
        payment = FinancialRecord.objects.get()
        self.assertEqual(payment.purpose_description, "Transport refund")
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_dues_ignore_purpose_and_allocations(self):
        self.client.post(reverse("finance_create"), self.data(record_type="due", amount="80.00", paid_amount="80.00", status="paid", **{self.alloc(self.c1): "80.00"}))
        due = FinancialRecord.objects.get()
        self.assertEqual(due.purpose, "")
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_repeat_submission_adds_no_allocations(self):
        key = uuid.uuid4()
        payload = self.data(key=key, **{self.alloc(self.c1): "400.00"})
        self.client.post(reverse("finance_create"), payload)
        response = self.client.post(reverse("finance_create"), payload)
        self.assertEqual(FinancialRecord.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 1)
        self.assertRedirects(response, reverse("finance_detail", args=[FinancialRecord.objects.get().pk]), fetch_redirect_response=False)

    def test_reused_key_with_changed_data_rejected(self):
        key = uuid.uuid4()
        self.client.post(reverse("finance_create"), self.data(key=key, **{self.alloc(self.c1): "400.00"}))
        response = self.client.post(reverse("finance_create"), self.data(key=key, **{self.alloc(self.c2): "300.00"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.active(), {self.c1.pk: D("400.00")})

    def _created_payment(self):
        self.client.post(reverse("finance_create"), self.data(**{self.alloc(self.c1): "400.00"}))
        return FinancialRecord.objects.get()

    def edit_data(self, **extra):
        d = self.data()
        d.pop("submission_key")
        d.update(extra)
        return d

    def test_moving_allocation_needs_reason_and_keeps_history(self):
        payment = self._created_payment()
        url = reverse("finance_edit", args=[payment.pk])
        response = self.client.post(url, self.edit_data(**{self.alloc(self.c2): "300.00", self.alloc(self.c1): "100.00"}))
        self.assertEqual(response.status_code, 200)  # reason missing
        self.assertEqual(self.active(payment), {self.c1.pk: D("400.00")})
        self.client.post(url, self.edit_data(allocation_change_reason="Wrong collection", **{self.alloc(self.c2): "300.00", self.alloc(self.c1): "100.00"}))
        self.assertEqual(self.active(payment), {self.c1.pk: D("100.00"), self.c2.pk: D("300.00")})
        removed = PaymentAllocation.objects.get(payment=payment, removed_at__isnull=False)
        self.assertEqual((removed.amount, removed.removal_reason, removed.removed_by), (D("400.00"), "Wrong collection", self.manager))

    def test_unchanged_edit_keeps_allocations_without_reason(self):
        payment = self._created_payment()
        self.client.post(reverse("finance_edit", args=[payment.pk]), self.edit_data(notes="Edited", **{self.alloc(self.c1): "400.00"}))
        payment.refresh_from_db()
        self.assertEqual(payment.notes, "Edited")
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 1)

    def test_lowering_paid_and_allocation_together(self):
        payment = self._created_payment()
        self.client.post(reverse("finance_edit", args=[payment.pk]), self.edit_data(paid_amount="200.00", allocation_change_reason="Paid amount corrected", **{self.alloc(self.c1): "200.00"}))
        payment.refresh_from_db()
        self.assertEqual(payment.paid_amount, D("200.00"))
        self.assertEqual(self.active(payment), {self.c1.pk: D("200.00")})

    def test_lowering_paid_below_allocations_rejected(self):
        payment = self._created_payment()
        response = self.client.post(reverse("finance_edit", args=[payment.pk]), self.edit_data(paid_amount="200.00", **{self.alloc(self.c1): "400.00"}))
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.paid_amount, D("400.00"))

    def test_collection_from_another_member_not_offered(self):
        other = Member.objects.create(organisation=self.org, created_by=self.manager, updated_by=self.manager, membership_number="P2", first_name="Oth", last_name="Er")
        foreign = CollectionRecord(organisation=self.org, member=other, crop=self.crop, quantity=D("10"), quantity_unit="kg", collection_date=date(2026, 9, 1), collection_location="Point", price_per_unit=D("5.00"), recorded_by=self.manager)
        foreign.total_value = foreign.calculate_total()
        foreign.save()
        self.client.post(reverse("finance_create"), self.data(**{self.alloc(self.c1): "350.00", self.alloc(foreign): "50.00"}))
        self.assertNotIn(foreign.pk, self.active())

    def test_finance_export_shows_allocated_and_unallocated_paid_money(self):
        import csv
        import io
        self.client.post(reverse("finance_create"), self.data(**{self.alloc(self.c1): "250.00"}))
        self.client.post(reverse("finance_create"), self.data(record_type="due", amount="80.00", paid_amount="80.00", status="paid", reference_number="QA-DUE"))
        payment = FinancialRecord.objects.get(record_type="member_payment")
        response = self.client.get(reverse("export_report", args=["finance", "csv"]))
        rows = {row["Reference"]: row for row in csv.DictReader(io.StringIO(response.content.decode()))}
        pay = rows["QA-PAY"]
        self.assertEqual(pay["Amount"], "1000.00")
        self.assertEqual(pay["Paid"], "400.00")
        self.assertEqual(pay["Purpose"], payment.get_purpose_display())
        self.assertEqual(pay["Allocated to collections"], "250.00")
        self.assertEqual(pay["Unallocated paid balance"], "150.00")
        due = rows["QA-DUE"]
        self.assertEqual((due["Purpose"], due["Allocated to collections"], due["Unallocated paid balance"]), ("", "", ""))
