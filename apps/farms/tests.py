from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .forms import FarmCropSeasonForm, FarmForm, FarmOwnershipTransferForm
from .models import Crop, Farm, FarmCropSeason, FarmOwnershipTransfer

User = get_user_model()


class FarmFixture(TestCase):
    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Cooperative", slug="alpha-farms", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Farmers", slug="beta-farms", currency="KES")
        self.admin = User.objects.create_user(email="admin@alpha.farm", password="StrongPass!42")
        self.manager = User.objects.create_user(email="manager@alpha.farm", password="StrongPass!42")
        self.field = User.objects.create_user(email="field@alpha.farm", password="StrongPass!42")
        self.beta_admin = User.objects.create_user(email="admin@beta.farm", password="StrongPass!42")
        self.membership(self.alpha, self.admin, OrganisationMembership.Role.ADMIN)
        self.membership(self.alpha, self.manager, OrganisationMembership.Role.MANAGER)
        self.membership(self.alpha, self.field, OrganisationMembership.Role.FIELD_OFFICER)
        self.membership(self.beta, self.beta_admin, OrganisationMembership.Role.ADMIN)
        self.alpha_member = self.member(self.alpha, self.admin, "A-F01", "Ama", "Mensah")
        self.beta_member = self.member(self.beta, self.beta_admin, "B-F01", "Ben", "Otieno")
        self.maize = Crop.objects.create(organisation=self.alpha, name="Maize", variety="Obatanpa")
        self.cocoa = Crop.objects.create(organisation=self.alpha, name="Cocoa")
        self.beta_crop = Crop.objects.create(organisation=self.beta, name="Coffee")
        self.alpha_farm = Farm.objects.create(organisation=self.alpha, member=self.alpha_member, name="North field", size=Decimal("2.50"), location="Tamale", latitude=Decimal("9.407500"), longitude=Decimal("-0.853300"))
        self.beta_farm = Farm.objects.create(organisation=self.beta, member=self.beta_member, name="Rift farm", location="Nakuru")
        self.season = FarmCropSeason.objects.create(organisation=self.alpha, farm=self.alpha_farm, crop=self.maize, season="2026 major", planting_start=date(2026, 4, 1), estimated_yield=Decimal("1200"))
        self.beta_season = FarmCropSeason.objects.create(organisation=self.beta, farm=self.beta_farm, crop=self.beta_crop, season="2026", actual_yield=Decimal("800"))

    @staticmethod
    def membership(organisation, user, role):
        return OrganisationMembership.objects.create(organisation=organisation, user=user, role=role)

    @staticmethod
    def member(organisation, actor, number, first, last):
        return Member.objects.create(organisation=organisation, created_by=actor, updated_by=actor, membership_number=number, first_name=first, last_name=last)

    def login_as(self, user, organisation=None):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = (organisation or self.alpha).pk
        session.save()

    def farm_payload(self, **overrides):
        data = {"member": str(self.alpha_member.pk), "name": "South field", "size": "3.25", "size_unit": Farm.SizeUnit.HECTARES, "location": "Yendi", "latitude": "9.442000", "longitude": "-0.009000", "notes": "Rain-fed"}
        data.update(overrides)
        return data

    def season_payload(self, **overrides):
        data = {"crop": str(self.cocoa.pk), "season": "2026 minor", "planting_start": "2026-08-01", "planting_end": "2026-08-14", "estimated_yield": "600", "actual_yield": "", "yield_unit": FarmCropSeason.YieldUnit.KILOGRAMS, "notes": ""}
        data.update(overrides)
        return data


class FarmIsolationTests(FarmFixture):
    def test_list_search_detail_and_member_profile_do_not_leak_tenants(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("farm_list"))
        self.assertContains(response, "North field")
        self.assertNotContains(response, "Rift farm")
        response = self.client.get(reverse("farm_list"), {"q": "Nakuru"})
        self.assertContains(response, "No farms match")
        self.assertNotContains(response, "Rift farm")
        self.assertEqual(self.client.get(reverse("farm_detail", args=[self.beta_farm.pk])).status_code, 404)
        response = self.client.get(reverse("member_detail", args=[self.alpha_member.pk]))
        self.assertContains(response, "North field")
        self.assertNotContains(response, "Rift farm")

    def test_guessed_cross_tenant_objects_cannot_be_edited_or_receive_seasons(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.get(reverse("farm_edit", args=[self.beta_farm.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("season_create", args=[self.beta_farm.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("crop_edit", args=[self.beta_crop.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("season_edit", args=[self.alpha_farm.pk, self.beta_season.pk])).status_code, 404)

    def test_form_choices_are_tenant_scoped(self):
        farm_form = FarmForm(organisation=self.alpha)
        self.assertIn(self.alpha_member, farm_form.fields["member"].queryset)
        self.assertNotIn(self.beta_member, farm_form.fields["member"].queryset)
        season_form = FarmCropSeasonForm(organisation=self.alpha, farm=self.alpha_farm)
        self.assertIn(self.maize, season_form.fields["crop"].queryset)
        self.assertNotIn(self.beta_crop, season_form.fields["crop"].queryset)

    def test_models_reject_cross_tenant_relationships(self):
        farm = Farm(organisation=self.alpha, member=self.beta_member, name="Invalid")
        with self.assertRaises(ValidationError):
            farm.full_clean()
        record = FarmCropSeason(organisation=self.alpha, farm=self.alpha_farm, crop=self.beta_crop, season="Invalid")
        with self.assertRaises(ValidationError):
            record.full_clean()


class FarmValidationTests(FarmFixture):
    def test_gps_requires_pair_and_valid_ranges(self):
        for latitude, longitude in ((Decimal("1"), None), (Decimal("91"), Decimal("0")), (Decimal("0"), Decimal("181"))):
            farm = Farm(organisation=self.alpha, member=self.alpha_member, name="Invalid GPS", latitude=latitude, longitude=longitude)
            with self.assertRaises(ValidationError):
                farm.full_clean()

    def test_negative_size_and_yields_are_rejected(self):
        farm = Farm(organisation=self.alpha, member=self.alpha_member, name="Negative", size=Decimal("-1"))
        with self.assertRaises(ValidationError):
            farm.full_clean()
        record = FarmCropSeason(organisation=self.alpha, farm=self.alpha_farm, crop=self.cocoa, season="Bad", estimated_yield=Decimal("-1"), actual_yield=Decimal("-2"))
        with self.assertRaises(ValidationError) as context:
            record.full_clean()
        self.assertEqual(set(context.exception.message_dict), {"estimated_yield", "actual_yield"})

    def test_planting_end_cannot_precede_start(self):
        record = FarmCropSeason(organisation=self.alpha, farm=self.alpha_farm, crop=self.cocoa, season="Bad dates", planting_start=date(2026, 8, 2), planting_end=date(2026, 8, 1))
        with self.assertRaises(ValidationError) as context:
            record.full_clean()
        self.assertIn("planting_end", context.exception.message_dict)

    def test_farm_and_crop_season_uniqueness(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Farm.objects.create(organisation=self.alpha, member=self.alpha_member, name="North field")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FarmCropSeason.objects.create(organisation=self.alpha, farm=self.alpha_farm, crop=self.maize, season="2026 major")


class FarmRoleAndWorkflowTests(FarmFixture):
    def test_operational_roles_view_and_field_officer_is_redirected_and_cannot_mutate(self):
        for user in (self.admin, self.manager):
            self.client.logout()
            self.login_as(user)
            self.assertEqual(self.client.get(reverse("farm_list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("farm_detail", args=[self.alpha_farm.pk])).status_code, 200)
            self.assertEqual(self.client.get(reverse("crop_list")).status_code, 200)
        self.client.logout()
        self.login_as(self.field)
        for url in (reverse("farm_list"), reverse("farm_detail", args=[self.alpha_farm.pk]), reverse("crop_list")):
            self.assertRedirects(self.client.get(url), reverse("field_home"), fetch_redirect_response=False)
        for url in (reverse("farm_create"), reverse("farm_edit", args=[self.alpha_farm.pk]), reverse("crop_create"), reverse("season_create", args=[self.alpha_farm.pk])):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse("farm_transfer", args=[self.alpha_farm.pk])).status_code, 403)

    def test_owner_transfer_records_chain_and_preserves_crop_history(self):
        successor = self.member(self.alpha, self.admin, "A-F02", "Kofi", "Asare")
        next_successor = self.member(self.alpha, self.admin, "A-F03", "Akua", "Boateng")
        self.login_as(self.manager)

        response = self.client.post(
            reverse("farm_transfer", args=[self.alpha_farm.pk]),
            {"successor_member": str(successor.pk), "reason": "Ownership inherited by family."},
        )
        self.assertRedirects(response, reverse("farm_detail", args=[self.alpha_farm.pk]))
        self.alpha_farm.refresh_from_db()
        self.assertEqual(self.alpha_farm.member, successor)
        self.assertEqual(self.alpha_farm.crop_seasons.get(), self.season)
        first_transfer = FarmOwnershipTransfer.objects.get(farm=self.alpha_farm)
        self.assertEqual(first_transfer.previous_member, self.alpha_member)
        self.assertEqual(first_transfer.successor_member, successor)
        self.assertEqual(first_transfer.transferred_by, self.manager)
        self.assertEqual(first_transfer.reason, "Ownership inherited by family.")

        response = self.client.post(
            reverse("farm_transfer", args=[self.alpha_farm.pk]),
            {"successor_member": str(next_successor.pk), "reason": "Second succession."},
        )
        self.assertRedirects(response, reverse("farm_detail", args=[self.alpha_farm.pk]))
        transfers = list(FarmOwnershipTransfer.objects.filter(farm=self.alpha_farm).order_by("transferred_at", "pk"))
        self.assertEqual(len(transfers), 2)
        self.assertEqual(transfers[1].previous_member, successor)
        self.assertEqual(transfers[1].successor_member, next_successor)
        self.assertContains(self.client.get(reverse("farm_detail", args=[self.alpha_farm.pk])), "Second succession.")

    def test_owner_transfer_rejects_cross_tenant_and_duplicate_farm_name(self):
        self.login_as(self.admin)
        response = self.client.post(
            reverse("farm_transfer", args=[self.alpha_farm.pk]),
            {"successor_member": str(self.beta_member.pk), "reason": "Invalid tenant."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FarmOwnershipTransfer.objects.exists())

        successor = self.member(self.alpha, self.admin, "A-F02", "Kofi", "Asare")
        Farm.objects.create(organisation=self.alpha, member=successor, name=self.alpha_farm.name)
        response = self.client.post(
            reverse("farm_transfer", args=[self.alpha_farm.pk]),
            {"successor_member": str(successor.pk), "reason": "Duplicate farm name."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.alpha_farm.refresh_from_db()
        self.assertEqual(self.alpha_farm.member, self.alpha_member)
        self.assertFalse(FarmOwnershipTransfer.objects.exists())

    def test_transfer_form_only_offers_active_members_of_the_current_tenant(self):
        inactive = self.member(self.alpha, self.admin, "A-F02", "Inactive", "Member")
        inactive.status = Member.Status.INACTIVE
        inactive.save(update_fields=["status"])
        form = FarmOwnershipTransferForm(organisation=self.alpha, current_member=self.alpha_member)
        self.assertNotIn(self.alpha_member, form.fields["successor_member"].queryset)
        self.assertNotIn(inactive, form.fields["successor_member"].queryset)
        self.assertNotIn(self.beta_member, form.fields["successor_member"].queryset)

    def test_admin_registers_farm_and_member_query_preselects_safely(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("farm_create"), {"member": self.alpha_member.pk})
        self.assertEqual(response.context["form"].initial["member"], self.alpha_member)
        response = self.client.get(reverse("farm_create"), {"member": self.beta_member.pk})
        self.assertNotIn("member", response.context["form"].initial)
        response = self.client.get(reverse("farm_create"), {"member": "not-a-uuid"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("member", response.context["form"].initial)
        response = self.client.post(reverse("farm_create"), self.farm_payload())
        farm = Farm.objects.get(organisation=self.alpha, name="South field")
        self.assertRedirects(response, reverse("farm_detail", args=[farm.pk]))
        self.assertEqual(farm.member, self.alpha_member)
        self.assertEqual(farm.gps, "9.442000, -0.009000")

    def test_manager_creates_crop_and_records_then_updates_season(self):
        self.login_as(self.manager)
        response = self.client.post(reverse("crop_create"), {"name": "Rice", "variety": "Jasmine", "is_active": "on"})
        self.assertRedirects(response, reverse("crop_list"))
        rice = Crop.objects.get(organisation=self.alpha, name="Rice")
        payload = self.season_payload(crop=str(rice.pk), season="2027 major")
        response = self.client.post(reverse("season_create", args=[self.alpha_farm.pk]), payload)
        record = FarmCropSeason.objects.get(farm=self.alpha_farm, crop=rice, season="2027 major")
        self.assertRedirects(response, reverse("farm_detail", args=[self.alpha_farm.pk]))
        payload["actual_yield"] = "550"
        response = self.client.post(reverse("season_edit", args=[self.alpha_farm.pk, record.pk]), payload)
        self.assertRedirects(response, reverse("farm_detail", args=[self.alpha_farm.pk]))
        record.refresh_from_db()
        self.assertEqual(record.actual_yield, Decimal("550"))

    def test_cross_tenant_posted_member_and_crop_are_rejected(self):
        self.login_as(self.admin)
        response = self.client.post(reverse("farm_create"), self.farm_payload(member=str(self.beta_member.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "member", "Select a valid choice. That choice is not one of the available choices.")
        response = self.client.post(reverse("season_create", args=[self.alpha_farm.pk]), self.season_payload(crop=str(self.beta_crop.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "crop", "Select a valid choice. That choice is not one of the available choices.")

    def test_search_crop_filter_and_malformed_filter_remain_tenant_safe(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("farm_list"), {"crop": self.maize.pk})
        self.assertContains(response, "North field")
        self.assertNotContains(response, "Rift farm")
        response = self.client.get(reverse("farm_list"), {"crop": self.beta_crop.pk})
        self.assertContains(response, "North field")
        self.assertNotContains(response, "Rift farm")
        response = self.client.get(reverse("farm_list"), {"crop": "not-a-uuid"})
        self.assertEqual(response.status_code, 200)

    def test_inactive_crop_is_unavailable_for_new_season_but_existing_record_is_visible(self):
        self.maize.is_active = False
        self.maize.save(update_fields=["is_active"])
        form = FarmCropSeasonForm(organisation=self.alpha, farm=self.alpha_farm)
        self.assertNotIn(self.maize, form.fields["crop"].queryset)
        edit_form = FarmCropSeasonForm(instance=self.season, organisation=self.alpha, farm=self.alpha_farm)
        self.assertIn(self.maize, edit_form.fields["crop"].queryset)
        self.login_as(self.admin)
        response = self.client.get(reverse("farm_detail", args=[self.alpha_farm.pk]))
        self.assertContains(response, "Maize")

    def test_suspended_organisation_cannot_access_farms(self):
        self.alpha.status = Organisation.Status.SUSPENDED
        self.alpha.save(update_fields=["status"])
        self.login_as(self.admin)
        self.assertRedirects(self.client.get(reverse("farm_list")), reverse("choose_organisation"))