"""Voiding collections (UAT I-5). See docs/architecture.md, Voiding collections."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.farms.models import Crop
from apps.finance.models import FinancialRecord, PaymentAllocation
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import CollectionRecord

User = get_user_model()
D = Decimal


class CollectionVoidTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Void Org", slug="void-org")
        self.manager = self.user("manager@void.test", "manager")
        self.admin = self.user("admin@void.test", "admin")
        self.officer = self.user("officer@void.test", "field_officer")
        self.member = Member.objects.create(organisation=self.org, created_by=self.admin, updated_by=self.admin, membership_number="V1", first_name="Vida", last_name="Void")
        self.crop = Crop.objects.create(organisation=self.org, name="Maize")
        self.keep = self.collection("100", "QA keep")  # 500.00
        self.dup = self.collection("50", "QA duplicate")  # 250.00

    def user(self, email, role):
        user = User.objects.create_user(email=email, password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=user, role=role)
        return user

    def collection(self, quantity, notes):
        return CollectionRecord.objects.create(
            organisation=self.org, member=self.member, crop=self.crop, quantity=D(quantity), quantity_unit="kg",
            collection_date=date(2026, 9, 1), collection_location="Point", price_per_unit=D("5.00"),
            recorded_by=self.manager, notes=notes,
        )

    def payment(self, purpose=FinancialRecord.Purpose.COLLECTIONS, status=FinancialRecord.Status.PAID):
        return FinancialRecord.objects.create(
            organisation=self.org, record_type=FinancialRecord.Type.MEMBER_PAYMENT, member=self.member,
            amount=D("200.00"), paid_amount=D("200.00"), payment_method="cash", status=status,
            payment_date=date(2026, 9, 5), recorded_by=self.manager, purpose=purpose,
        )

    def allocate(self, payment, collection, amount="100.00"):
        return PaymentAllocation.objects.create(organisation=self.org, payment=payment, collection=collection, amount=D(amount), created_by=self.manager)

    def login(self, user):
        self.client.logout()
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    def url(self, record=None):
        return reverse("collection_void", args=[(record or self.dup).pk])

    def refresh(self):
        self.dup.refresh_from_db()
        return self.dup

    def test_field_officer_cannot_void(self):
        self.login(self.officer)
        self.assertNotEqual(self.client.get(self.url()).status_code, 200)
        self.client.post(self.url(), {"void_reason": "x"})
        self.assertFalse(self.refresh().is_voided)

    def test_reason_required(self):
        self.login(self.manager)
        response = self.client.post(self.url(), {"void_reason": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.refresh().is_voided)

    def test_manager_voids_with_reason_and_audit_is_kept(self):
        self.login(self.manager)
        response = self.client.post(self.url(), {"void_reason": "Duplicate entry"})
        self.assertRedirects(response, reverse("collection_detail", args=[self.dup.pk]), fetch_redirect_response=False)
        record = self.refresh()
        self.assertTrue(record.is_voided)
        self.assertEqual(record.voided_by, self.manager)
        self.assertEqual(record.void_reason, "Duplicate entry")
        self.assertIsNone(record.void_review)
        detail = self.client.get(reverse("collection_detail", args=[self.dup.pk]))
        self.assertContains(detail, "Voided collection.")
        self.assertContains(detail, "Duplicate entry")
        self.assertNotContains(detail, self.url())

    def test_active_allocation_blocks_void(self):
        self.allocate(self.payment(), self.dup)
        self.login(self.admin)
        page = self.client.get(self.url())
        self.assertContains(page, "cannot be voided yet")
        self.assertContains(page, "Do not cancel a genuine payment")
        self.client.post(self.url(), {"void_reason": "Duplicate"})
        self.assertFalse(self.refresh().is_voided)

    def test_removed_allocation_no_longer_blocks(self):
        allocation = self.allocate(self.payment(), self.dup)
        allocation.removed_at = timezone.now()
        allocation.removed_by = self.manager
        allocation.removal_reason = "Wrong collection"
        allocation.save()
        self.login(self.manager)
        self.client.post(self.url(), {"void_reason": "Duplicate"})
        self.assertTrue(self.refresh().is_voided)

    def test_cancelled_payment_allocation_does_not_block(self):
        payment = self.payment()
        self.allocate(payment, self.dup)
        FinancialRecord.objects.filter(pk=payment.pk).update(status=FinancialRecord.Status.CANCELLED)
        self.login(self.manager)
        self.client.post(self.url(), {"void_reason": "Duplicate"})
        self.assertTrue(self.refresh().is_voided)

    def test_unresolved_payments_require_review(self):
        unresolved = self.payment(purpose="")
        self.login(self.manager)
        page = self.client.get(self.url())
        self.assertContains(page, "Payments to review")
        self.assertContains(page, reverse("finance_detail", args=[unresolved.pk]))
        self.client.post(self.url(), {"void_reason": "Duplicate"})
        self.assertFalse(self.refresh().is_voided)  # review missing
        self.client.post(self.url(), {"void_reason": "Duplicate", "reviewed": "on", "review_decision": "related", "review_reason": "Paid for this one"})
        self.assertFalse(self.refresh().is_voided)  # related blocks
        self.client.post(self.url(), {"void_reason": "Duplicate", "reviewed": "on", "review_decision": "not_related", "review_reason": "Advance for seeds"})
        record = self.refresh()
        self.assertTrue(record.is_voided)
        self.assertEqual(record.void_review, {"decision": "not_related", "reason": "Advance for seeds", "payment_ids": [str(unresolved.pk)]})

    def test_voided_excluded_from_dashboard_and_export(self):
        self.login(self.manager)
        self.client.post(self.url(), {"void_reason": "Duplicate"})
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.context["metrics"]["collections"], 1)
        export = self.client.get(reverse("export_report", args=["collections", "csv"]))
        body = b"".join(export.streaming_content).decode() if export.streaming else export.content.decode()
        self.assertNotIn("QA duplicate", body)
        self.assertEqual(len(body.strip().splitlines()), 2)  # header + kept collection

    def test_voided_collection_cannot_be_edited_or_newly_allocated(self):
        self.login(self.manager)
        self.client.post(self.url(), {"void_reason": "Duplicate"})
        response = self.client.get(reverse("collection_edit", args=[self.dup.pk]))
        self.assertRedirects(response, reverse("collection_detail", args=[self.dup.pk]), fetch_redirect_response=False)
        bad = PaymentAllocation(organisation=self.org, payment=self.payment(), collection=self.refresh(), amount=D("10.00"), created_by=self.manager)
        with self.assertRaises(Exception):
            bad.full_clean()
