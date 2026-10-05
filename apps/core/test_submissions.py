"""Duplicate-submission protection (UAT issue I-2)."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.collections.models import CollectionRecord
from apps.core import submissions
from apps.farms.models import Crop
from apps.field.models import FieldVisit
from apps.finance.models import FinancialRecord
from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

User = get_user_model()


class SubmissionFixture(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Sub Org", slug="sub-org")
        self.admin = User.objects.create_user(email="admin@sub.test", password="x")
        self.manager = User.objects.create_user(email="manager@sub.test", password="x")
        self.field = User.objects.create_user(email="field@sub.test", password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=self.admin, role="admin")
        OrganisationMembership.objects.create(organisation=self.org, user=self.manager, role="manager")
        self.field_membership = OrganisationMembership.objects.create(organisation=self.org, user=self.field, role="field_officer")
        self.member = Member.objects.create(
            organisation=self.org, created_by=self.admin, updated_by=self.admin,
            membership_number="S1", first_name="Sam", last_name="Sub",
        )
        unit = StructureUnit.objects.create(organisation=self.org, name="G", unit_type="group", field_officer=self.field_membership)
        GroupMemberAssignment.objects.create(organisation=self.org, unit=unit, member=self.member)
        self.crop = Crop.objects.create(organisation=self.org, name="Maize")

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    def fresh_key(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        key = response.context["form"].initial.get(submissions.FIELD_NAME)
        self.assertIsNotNone(key)
        self.assertContains(response, 'name="submission_key"')
        return str(key)

    def collection_data(self, key, quantity="50"):
        return {
            "member": self.member.pk, "crop": self.crop.pk, "quantity": quantity,
            "quantity_unit": "kg", "collection_date": "2026-10-01",
            "collection_location": "Farm gate", "quality_grade": "A",
            "price_per_unit": "3", "notes": "", "submission_key": key,
        }


class CollectionSubmissionTests(SubmissionFixture):
    def test_exact_repeat_creates_one_record_and_returns_it(self):
        self.login(self.admin)
        url = reverse("collection_create")
        data = self.collection_data(self.fresh_key(url))
        first = self.client.post(url, data)
        second = self.client.post(url, data, follow=True)
        self.assertEqual(CollectionRecord.objects.count(), 1)
        record = CollectionRecord.objects.get()
        self.assertRedirects(first, reverse("collection_detail", args=[record.pk]))
        self.assertRedirects(second, reverse("collection_detail", args=[record.pk]))
        self.assertContains(second, "This collection was already saved.")

    def test_reused_key_with_changed_data_is_rejected_and_input_kept(self):
        self.login(self.admin)
        url = reverse("collection_create")
        key = self.fresh_key(url)
        self.client.post(url, self.collection_data(key))
        response = self.client.post(url, self.collection_data(key, quantity="75"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already submitted with different details")
        self.assertContains(response, 'value="75"')
        self.assertEqual(CollectionRecord.objects.count(), 1)

    def test_reused_key_by_another_user_is_rejected(self):
        self.login(self.admin)
        url = reverse("collection_create")
        data = self.collection_data(self.fresh_key(url))
        self.client.post(url, data)
        self.client.logout()
        self.login(self.manager)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already submitted with different details")
        self.assertEqual(CollectionRecord.objects.count(), 1)

    def test_separate_forms_with_identical_values_create_two_records(self):
        self.login(self.admin)
        url = reverse("collection_create")
        self.client.post(url, self.collection_data(self.fresh_key(url)))
        self.client.post(url, self.collection_data(self.fresh_key(url)))
        self.assertEqual(CollectionRecord.objects.count(), 2)

    def test_simultaneous_insert_returns_the_winning_record(self):
        self.login(self.admin)
        url = reverse("collection_create")
        data = self.collection_data(self.fresh_key(url))
        self.client.post(url, data)
        winner = CollectionRecord.objects.get()
        real = submissions._matching_existing
        calls = {"n": 0}

        def first_lookup_misses(*args, **kwargs):
            calls["n"] += 1
            return None if calls["n"] == 1 else real(*args, **kwargs)

        with mock.patch.object(submissions, "_matching_existing", side_effect=first_lookup_misses):
            response = self.client.post(url, data)
        self.assertEqual(calls["n"], 2, "database constraint path was not exercised")
        self.assertRedirects(response, reverse("collection_detail", args=[winner.pk]))
        self.assertEqual(CollectionRecord.objects.count(), 1)

    def test_edit_form_has_no_submission_key(self):
        self.login(self.admin)
        url = reverse("collection_create")
        self.client.post(url, self.collection_data(self.fresh_key(url)))
        record = CollectionRecord.objects.get()
        response = self.client.get(reverse("collection_edit", args=[record.pk]))
        self.assertNotContains(response, 'name="submission_key"')


class FieldSubmissionTests(SubmissionFixture):
    def test_field_collection_repeat_creates_one_record(self):
        self.login(self.field)
        url = reverse("field_collection_add", args=[self.member.pk])
        data = self.collection_data(self.fresh_key(url))
        self.client.post(url, data)
        self.client.post(url, data)
        self.assertEqual(CollectionRecord.objects.count(), 1)

    def test_field_visit_repeat_creates_one_visit(self):
        self.login(self.field)
        url = reverse("field_visit_add", args=[self.member.pk])
        data = {"visit_date": "2026-10-01", "notes": "Healthy crop", "latitude": "5", "longitude": "-1", "submission_key": self.fresh_key(url)}
        self.client.post(url, data)
        response = self.client.post(url, data, follow=True)
        self.assertEqual(FieldVisit.objects.count(), 1)
        self.assertContains(response, "This field visit was already saved.")


class FinanceSubmissionTests(SubmissionFixture):
    def finance_data(self, key, amount="100"):
        return {
            "record_type": "due", "member": self.member.pk, "amount": amount, "paid_amount": "0",
            "payment_method": "cash", "status": "pending", "payment_date": "2026-10-01",
            "reference_number": "", "notes": "", "submission_key": key,
        }

    def test_finance_repeat_creates_one_record(self):
        self.login(self.admin)
        url = reverse("finance_create")
        data = self.finance_data(self.fresh_key(url))
        self.client.post(url, data)
        self.client.post(url, data)
        self.assertEqual(FinancialRecord.objects.count(), 1)

    def test_finance_reused_key_with_changed_amount_is_rejected(self):
        self.login(self.admin)
        url = reverse("finance_create")
        key = self.fresh_key(url)
        self.client.post(url, self.finance_data(key))
        response = self.client.post(url, self.finance_data(key, amount="200"))
        self.assertContains(response, "already submitted with different details")
        self.assertEqual(FinancialRecord.objects.count(), 1)
