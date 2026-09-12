from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.collections.models import CollectionRecord
from apps.farms.models import Farm
from apps.field.models import FieldVisit
from apps.finance.models import FinancialRecord
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
        self.assertEqual(
            OrganisationMembership.objects.filter(organisation=self.organisation).count(), 4
        )
        self.assertFalse(
            MemberHistory.objects.for_organisation(self.organisation).exclude(changes={}).exists()
        )

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
