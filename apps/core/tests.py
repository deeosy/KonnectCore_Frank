from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.collections.models import CollectionRecord
from apps.farms.models import Farm
from apps.field.models import FieldVisit
from apps.finance.models import FinancialRecord, PaymentAllocation
from apps.groups.models import StructureUnit
from apps.members.models import Member, MemberHistory
from apps.organisations.models import Organisation, OrganisationMembership


class SeedDemoDataCommandTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            email="owner@example.com", password="test-password", first_name="Demo", last_name="Owner"
        )
        self.organisation = Organisation.objects.create(
            name="Demo Cooperative", slug="demo-command", currency="GHS"
        )
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=user,
            role=OrganisationMembership.Role.ADMIN,
        )
        self.other = Organisation.objects.create(
            name="Private Cooperative", slug="private-command", currency="GHS"
        )

    def test_seed_is_idempotent_and_tenant_scoped(self):
        call_command("seed_demo_data", organisation=self.organisation.slug)
        first = self._counts(self.organisation)
        call_command("seed_demo_data", organisation=self.organisation.slug)

        self.assertEqual(self._counts(self.organisation), first)
        self.assertEqual(first, (24, 4, 24, 34, 31, 12))
        self.assertEqual(self._counts(self.other), (0, 0, 0, 0, 0, 0))
        demo_member = Member.objects.get(organisation=self.organisation, membership_number="KC-001")
        self.assertEqual(demo_member.id_type, Member.IDType.GHANA_CARD)
        self.assertEqual(demo_member.id_number, "GHA-820000000")
        self.assertEqual(
            OrganisationMembership.objects.filter(organisation=self.organisation).count(), 4
        )
        self.assertFalse(
            MemberHistory.objects.for_organisation(self.organisation).exclude(changes={}).exists()
        )

    def test_seeded_member_payments_have_purpose_and_full_allocations(self):
        call_command("seed_demo_data", organisation=self.organisation.slug)
        call_command("seed_demo_data", organisation=self.organisation.slug)
        payments = FinancialRecord.objects.for_organisation(self.organisation).filter(
            record_type=FinancialRecord.Type.MEMBER_PAYMENT
        )
        self.assertEqual(payments.count(), 7)
        self.assertFalse(payments.filter(purpose="").exists())
        active = PaymentAllocation.objects.filter(organisation=self.organisation, removed_at__isnull=True)
        self.assertEqual(active.count(), 7)
        for payment in payments:
            allocations = list(active.filter(payment=payment))
            self.assertEqual(sum(a.amount for a in allocations), payment.paid_amount)
            self.assertTrue(all(a.collection.member_id == payment.member_id for a in allocations))

    @staticmethod
    def _counts(organisation):
        return (
            Member.objects.for_organisation(organisation).count(),
            StructureUnit.objects.for_organisation(organisation).filter(
                unit_type=StructureUnit.Type.GROUP
            ).count(),
            Farm.objects.for_organisation(organisation).count(),
            CollectionRecord.objects.for_organisation(organisation).count(),
            FinancialRecord.objects.for_organisation(organisation).count(),
            FieldVisit.objects.for_organisation(organisation).count(),
        )
