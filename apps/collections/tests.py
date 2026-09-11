import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.farms.models import Crop
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .forms import CollectionRecordForm
from .models import CollectionRecord

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="konnectcore-collection-tests-")
TINY_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CollectionFixture(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Cooperative", slug="alpha-collections", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Farmers", slug="beta-collections", currency="KES")
        self.admin = User.objects.create_user(email="admin@alpha.collection", password="StrongPass!42")
        self.manager = User.objects.create_user(email="manager@alpha.collection", password="StrongPass!42")
        self.field = User.objects.create_user(email="field@alpha.collection", password="StrongPass!42")
        self.beta_admin = User.objects.create_user(email="admin@beta.collection", password="StrongPass!42")
        self.membership(self.alpha, self.admin, OrganisationMembership.Role.ADMIN)
        self.membership(self.alpha, self.manager, OrganisationMembership.Role.MANAGER)
        self.membership(self.alpha, self.field, OrganisationMembership.Role.FIELD_OFFICER)
        self.membership(self.beta, self.beta_admin, OrganisationMembership.Role.ADMIN)
        self.alpha_member = self.member(self.alpha, self.admin, "A-C01", "Ama", "Mensah")
        self.alpha_member_two = self.member(self.alpha, self.admin, "A-C02", "Kojo", "Asare")
        self.beta_member = self.member(self.beta, self.beta_admin, "B-C01", "Ben", "Otieno")
        self.maize = Crop.objects.create(organisation=self.alpha, name="Maize", variety="Obatanpa")
        self.cocoa = Crop.objects.create(organisation=self.alpha, name="Cocoa")
        self.beta_crop = Crop.objects.create(organisation=self.beta, name="Coffee")
        self.alpha_record = self.record(
            self.alpha, self.alpha_member, self.maize, self.admin, "10.50", "3.25", date(2026, 9, 10), "Tamale depot"
        )
        self.beta_record = self.record(
            self.beta, self.beta_member, self.beta_crop, self.beta_admin, "8", "5", date(2026, 9, 9), "Nakuru depot"
        )

    @staticmethod
    def membership(organisation, user, role):
        return OrganisationMembership.objects.create(organisation=organisation, user=user, role=role)

    @staticmethod
    def member(organisation, actor, number, first, last):
        return Member.objects.create(
            organisation=organisation, created_by=actor, updated_by=actor,
            membership_number=number, first_name=first, last_name=last,
        )

    @staticmethod
    def record(organisation, member, crop, recorder, quantity, price, collected, location, **kwargs):
        return CollectionRecord.objects.create(
            organisation=organisation, member=member, crop=crop, recorded_by=recorder,
            quantity=Decimal(quantity), quantity_unit=CollectionRecord.QuantityUnit.KILOGRAMS,
            price_per_unit=Decimal(price), collection_date=collected,
            collection_location=location, **kwargs,
        )

    def login_as(self, user, organisation=None):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = (organisation or self.alpha).pk
        session.save()

    def payload(self, **overrides):
        data = {
            "member": str(self.alpha_member_two.pk), "crop": str(self.cocoa.pk),
            "quantity": "12.50", "quantity_unit": CollectionRecord.QuantityUnit.BAGS,
            "collection_date": "2026-09-11", "collection_location": "Yendi centre",
            "quality_grade": "A", "price_per_unit": "4.20", "notes": "Dry produce",
        }
        data.update(overrides)
        return data


class CollectionIsolationTests(CollectionFixture):
    def test_list_search_detail_and_member_history_never_leak_tenants(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("collection_list"))
        self.assertContains(response, "Tamale depot")
        self.assertNotContains(response, "Nakuru depot")
        response = self.client.get(reverse("collection_list"), {"q": "Nakuru"})
        self.assertContains(response, "No collection records match")
        self.assertNotContains(response, "Nakuru depot")
        self.assertEqual(self.client.get(reverse("collection_detail", args=[self.beta_record.pk])).status_code, 404)
        response = self.client.get(reverse("member_detail", args=[self.alpha_member.pk]))
        self.assertContains(response, "Collection history")
        self.assertContains(response, "Maize")
        self.assertNotContains(response, "Coffee")

    def test_cross_tenant_record_cannot_be_edited_or_its_photo_accessed(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.get(reverse("collection_edit", args=[self.beta_record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("collection_photo", args=[self.beta_record.pk])).status_code, 404)

    def test_form_choices_and_posted_foreign_keys_are_tenant_scoped(self):
        form = CollectionRecordForm(organisation=self.alpha, recorded_by=self.admin)
        self.assertIn(self.alpha_member, form.fields["member"].queryset)
        self.assertNotIn(self.beta_member, form.fields["member"].queryset)
        self.assertIn(self.maize, form.fields["crop"].queryset)
        self.assertNotIn(self.beta_crop, form.fields["crop"].queryset)
        self.login_as(self.admin)
        response = self.client.post(reverse("collection_create"), self.payload(member=str(self.beta_member.pk)))
        self.assertFormError(response.context["form"], "member", "Select a valid choice. That choice is not one of the available choices.")
        response = self.client.post(reverse("collection_create"), self.payload(crop=str(self.beta_crop.pk)))
        self.assertFormError(response.context["form"], "crop", "Select a valid choice. That choice is not one of the available choices.")

    def test_model_rejects_cross_tenant_relationships_and_recorder(self):
        invalid = CollectionRecord(
            organisation=self.alpha, member=self.beta_member, crop=self.beta_crop,
            recorded_by=self.beta_admin, quantity=Decimal("1"), price_per_unit=Decimal("2"),
            collection_date=date(2026, 9, 11), collection_location="Depot", total_value=Decimal("2"),
        )
        with self.assertRaises(ValidationError) as context:
            invalid.full_clean()
        self.assertEqual(set(context.exception.message_dict), {"member", "crop", "recorded_by"})


class CollectionWorkflowTests(CollectionFixture):
    def test_admin_creates_collection_with_server_recorder_and_automatic_total(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("collection_create"), {"member": self.alpha_member_two.pk})
        self.assertEqual(str(response.context["form"].initial["member"]), str(self.alpha_member_two.pk))
        response = self.client.get(reverse("collection_create"), {"member": "not-a-uuid"})
        self.assertNotIn("member", response.context["form"].initial)
        response = self.client.post(reverse("collection_create"), self.payload())
        record = CollectionRecord.objects.get(organisation=self.alpha, member=self.alpha_member_two)
        self.assertRedirects(response, reverse("collection_detail", args=[record.pk]))
        self.assertEqual(record.recorded_by, self.admin)
        self.assertEqual(record.total_value, Decimal("52.50"))

    def test_manager_edits_values_recalculates_total_and_preserves_original_recorder(self):
        self.login_as(self.manager)
        response = self.client.post(
            reverse("collection_edit", args=[self.alpha_record.pk]),
            self.payload(member=str(self.alpha_member.pk), crop=str(self.maize.pk), quantity="2.55", price_per_unit="1.11"),
        )
        self.assertRedirects(response, reverse("collection_detail", args=[self.alpha_record.pk]))
        self.alpha_record.refresh_from_db()
        self.assertEqual(self.alpha_record.total_value, Decimal("2.83"))
        self.assertEqual(self.alpha_record.recorded_by, self.admin)

    def test_update_fields_also_updates_calculated_total(self):
        self.alpha_record.quantity = Decimal("2")
        self.alpha_record.save(update_fields=["quantity"])
        self.alpha_record.refresh_from_db()
        self.assertEqual(self.alpha_record.total_value, Decimal("6.50"))

    def test_inactive_crop_is_unavailable_for_new_records_but_existing_record_can_be_edited(self):
        self.maize.is_active = False
        self.maize.save(update_fields=["is_active"])
        create_form = CollectionRecordForm(organisation=self.alpha, recorded_by=self.admin)
        edit_form = CollectionRecordForm(instance=self.alpha_record, organisation=self.alpha, recorded_by=self.manager)
        self.assertNotIn(self.maize, create_form.fields["crop"].queryset)
        self.assertIn(self.maize, edit_form.fields["crop"].queryset)

    def test_historical_record_remains_editable_after_original_recorder_is_inactive(self):
        membership = OrganisationMembership.objects.get(organisation=self.alpha, user=self.admin)
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        form = CollectionRecordForm(
            self.payload(member=str(self.alpha_member.pk), crop=str(self.maize.pk)),
            instance=self.alpha_record, organisation=self.alpha, recorded_by=self.manager,
        )
        self.assertTrue(form.is_valid(), form.errors)


class CollectionPermissionAndFilterTests(CollectionFixture):
    def test_all_roles_can_view_but_field_officer_cannot_mutate(self):
        for user in (self.admin, self.manager, self.field):
            self.client.logout()
            self.login_as(user)
            self.assertEqual(self.client.get(reverse("collection_list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("collection_detail", args=[self.alpha_record.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("collection_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("collection_edit", args=[self.alpha_record.pk])).status_code, 403)

    def test_member_crop_and_date_filters_are_tenant_scoped(self):
        self.record(self.alpha, self.alpha_member_two, self.cocoa, self.manager, "4", "2", date(2026, 8, 1), "Accra centre")
        self.login_as(self.admin)
        response = self.client.get(reverse("collection_list"), {
            "member": self.alpha_member.pk, "crop": self.maize.pk,
            "date_from": "2026-09-01", "date_to": "2026-09-30",
        })
        self.assertContains(response, "Tamale depot")
        self.assertNotContains(response, "Accra centre")
        self.assertNotContains(response, "Nakuru depot")

    def test_foreign_and_malformed_filters_never_error_or_leak(self):
        self.login_as(self.admin)
        for params in ({"crop": self.beta_crop.pk}, {"member": self.beta_member.pk}, {"crop": "bad", "date_from": "invalid"}):
            response = self.client.get(reverse("collection_list"), params)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Tamale depot")
            self.assertNotContains(response, "Nakuru depot")

    def test_suspended_organisation_cannot_access_collections(self):
        self.alpha.status = Organisation.Status.SUSPENDED
        self.alpha.save(update_fields=["status"])
        self.login_as(self.admin)
        self.assertRedirects(self.client.get(reverse("collection_list")), reverse("choose_organisation"))


class CollectionValidationAndPhotoTests(CollectionFixture):
    def test_invalid_quantity_price_and_location_are_rejected(self):
        invalid = CollectionRecord(
            organisation=self.alpha, member=self.alpha_member, crop=self.maize, recorded_by=self.admin,
            quantity=Decimal("0"), price_per_unit=Decimal("-1"), collection_date=date(2026, 9, 11),
            collection_location=" ", total_value=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as context:
            invalid.full_clean()
        self.assertEqual(set(context.exception.message_dict), {"quantity", "price_per_unit", "collection_location"})

    def test_database_constraints_reject_invalid_values(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.record(self.alpha, self.alpha_member, self.maize, self.admin, "0", "1", date(2026, 9, 11), "Depot")

    def test_photo_is_private_and_tenant_checked(self):
        self.alpha_record.photo = SimpleUploadedFile("produce.gif", TINY_GIF, content_type="image/gif")
        self.alpha_record.save(update_fields=["photo"])
        self.login_as(self.admin)
        response = self.client.get(reverse("collection_photo", args=[self.alpha_record.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/*")
        self.assertEqual(self.client.get(reverse("collection_photo", args=[self.beta_record.pk])).status_code, 404)

    def test_missing_and_oversized_photos_are_rejected_safely(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.get(reverse("collection_photo", args=[self.alpha_record.pk])).status_code, 404)
        oversized = SimpleUploadedFile("large.jpg", b"x" * (5 * 1024 * 1024 + 1), content_type="image/jpeg")
        form = CollectionRecordForm(
            self.payload(), {"photo": oversized}, organisation=self.alpha, recorded_by=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Photo must be 5 MB or smaller.", form.errors["photo"])