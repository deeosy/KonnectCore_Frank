from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .forms import FarmCropSeasonForm
from .models import Crop, Farm, FarmCropSeason

User = get_user_model()


class HarvestCoordinationTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.reference_date = today
        self.alpha = Organisation.objects.create(name="Harvest Org", slug="harvest-org")
        self.beta = Organisation.objects.create(name="Other Harvest Org", slug="other-harvest-org")
        self.admin = self.create_user("admin@harvest.test", self.alpha, OrganisationMembership.Role.ADMIN)
        self.officer = self.create_user("officer@harvest.test", self.alpha, OrganisationMembership.Role.FIELD_OFFICER)
        self.beta_admin = self.create_user("admin@other-harvest.test", self.beta, OrganisationMembership.Role.ADMIN)

        self.visible_member = self.create_member(self.alpha, self.admin, "A1", "Ama", "Visible")
        self.other_member = self.create_member(self.alpha, self.admin, "A2", "Kojo", "Other")
        self.beta_member = self.create_member(self.beta, self.beta_admin, "B1", "Beta", "Farmer")

        officer_membership = OrganisationMembership.objects.get(user=self.officer, organisation=self.alpha)
        unit = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Officer group",
            unit_type=StructureUnit.Type.GROUP,
            field_officer=officer_membership,
        )
        GroupMemberAssignment.objects.create(organisation=self.alpha, unit=unit, member=self.visible_member)
        self.unit = unit

        self.maize = Crop.objects.create(organisation=self.alpha, name="Maize")
        self.cocoa = Crop.objects.create(organisation=self.alpha, name="Cocoa")
        self.beta_crop = Crop.objects.create(organisation=self.beta, name="Coffee")

        self.visible_farm = Farm.objects.create(
            organisation=self.alpha, member=self.visible_member, name="North field", location="Tamale"
        )
        self.other_farm = Farm.objects.create(
            organisation=self.alpha, member=self.other_member, name="South field", location="Tamale"
        )
        self.yendi_farm = Farm.objects.create(
            organisation=self.alpha, member=self.other_member, name="East field", location="Yendi"
        )
        self.beta_farm = Farm.objects.create(
            organisation=self.beta, member=self.beta_member, name="Beta field", location="Nakuru"
        )

        self.visible_season = self.create_season(
            self.visible_farm, self.maize, "2026 major", today + timedelta(days=1)
        )
        self.create_season(self.other_farm, self.maize, "2026 major", today + timedelta(days=5))
        self.create_season(self.visible_farm, self.maize, "2026 late", today + timedelta(days=20))
        self.create_season(self.yendi_farm, self.maize, "2026 major", today + timedelta(days=1))
        self.create_season(self.visible_farm, self.cocoa, "2026 major", today + timedelta(days=1))
        self.beta_season = self.create_season(
            self.beta_farm, self.beta_crop, "2026", today + timedelta(days=1)
        )

    @staticmethod
    def create_user(email, organisation, role):
        user = User.objects.create_user(email=email, password="test-password")
        OrganisationMembership.objects.create(organisation=organisation, user=user, role=role)
        return user

    @staticmethod
    def create_member(organisation, actor, number, first, last):
        return Member.objects.create(
            organisation=organisation,
            created_by=actor,
            updated_by=actor,
            membership_number=number,
            first_name=first,
            last_name=last,
        )

    @staticmethod
    def create_season(farm, crop, season, harvest_date):
        return FarmCropSeason.objects.create(
            organisation=farm.organisation,
            farm=farm,
            crop=crop,
            season=season,
            expected_harvest_date=harvest_date,
        )

    def login(self, user, organisation=None):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = (organisation or self.alpha).pk
        session.save()

    def test_harvest_groups_cluster_same_crop_location_and_date_window(self):
        groups = FarmCropSeason.harvest_groups(
            self.alpha, reference_date=self.reference_date, window_days=7
        )

        self.assertEqual(len(groups), 3)
        by_key = {(group["crop"].name, group["location"], group["member_count"]) for group in groups}
        self.assertIn(("Maize", "Tamale", 2), by_key)
        self.assertIn(("Maize", "Yendi", 1), by_key)
        self.assertIn(("Cocoa", "Tamale", 1), by_key)
        self.assertNotIn("Coffee", {group["crop"].name for group in groups})

    def test_harvest_window_filters_by_crop_date_and_member_scope(self):
        window = FarmCropSeason.harvest_window(
            self.alpha, reference_date=self.reference_date, window_days=7
        )
        self.assertEqual(window.count(), 4)

        maize = FarmCropSeason.harvest_window(
            self.alpha, crop=self.maize, reference_date=self.reference_date, window_days=7
        )
        self.assertEqual(maize.count(), 3)

        scoped = FarmCropSeason.harvest_window(
            self.alpha,
            reference_date=self.reference_date,
            window_days=7,
            member_ids=self.visible_member.__class__.objects.filter(pk=self.visible_member.pk).values("pk"),
        )
        self.assertEqual(scoped.count(), 2)

    def test_field_officer_only_sees_assigned_members_on_dashboard(self):
        self.login(self.officer)
        response = self.client.get(reverse("harvest_coordination"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ama Visible")
        self.assertNotContains(response, "Kojo Other")

        self.login(self.admin)
        response = self.client.get(reverse("harvest_coordination"))
        self.assertContains(response, "Ama Visible")
        self.assertContains(response, "Kojo Other")

    def test_harvest_dashboard_can_filter_by_crop(self):
        self.login(self.admin)
        response = self.client.get(reverse("harvest_coordination"), {"crop": self.cocoa.pk})
        self.assertContains(response, "Cocoa · Tamale")
        self.assertNotContains(response, "Kojo Other")
        self.assertNotContains(response, "2026 late")

    def test_expected_harvest_date_is_saved_and_shown_on_farm(self):
        self.login(self.admin)
        response = self.client.post(
            reverse("season_create", args=[self.visible_farm.pk]),
            {
                "crop": str(self.cocoa.pk),
                "season": "2027 major",
                "planting_start": "2027-03-01",
                "planting_end": "2027-03-15",
                "expected_harvest_date": "2027-08-20",
                "estimated_yield": "400",
                "actual_yield": "",
                "yield_unit": FarmCropSeason.YieldUnit.KILOGRAMS,
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("farm_detail", args=[self.visible_farm.pk]))
        season = FarmCropSeason.objects.get(farm=self.visible_farm, crop=self.cocoa, season="2027 major")
        self.assertEqual(season.expected_harvest_date.isoformat(), "2027-08-20")
        response = self.client.get(reverse("farm_detail", args=[self.visible_farm.pk]))
        self.assertContains(response, "Expected harvest: 2027-08-20")

    def test_form_accepts_expected_harvest_date(self):
        form = FarmCropSeasonForm(
            data={
                "crop": str(self.maize.pk),
                "season": "2027 minor",
                "planting_start": "2027-04-01",
                "planting_end": "2027-04-10",
                "expected_harvest_date": "2027-09-01",
                "estimated_yield": "100",
                "actual_yield": "",
                "yield_unit": FarmCropSeason.YieldUnit.KILOGRAMS,
                "notes": "",
            },
            organisation=self.alpha,
            farm=self.visible_farm,
        )
        self.assertTrue(form.is_valid(), form.errors)
        season = form.save()
        self.assertEqual(season.expected_harvest_date.isoformat(), "2027-09-01")
