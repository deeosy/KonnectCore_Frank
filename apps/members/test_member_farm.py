"""Phase 2 of Kennedy's feedback (items 1+4): farm and crops captured while adding a member."""
from django.urls import reverse

from apps.farms.models import Farm, FarmCropSeason
from apps.farms.tests import FarmFixture

from .models import Member, MemberHistory


class AddMemberWithFarmTests(FarmFixture):
    def payload(self, number="A-NEW1", **farm):
        data = {
            "first_name": "Kofi", "last_name": "Boateng", "phone": "+233200000099",
            "membership_number": number, "id_reference": "ID-99", "location": "Tamale town",
            "status": Member.Status.ACTIVE,
        }
        data.update({f"farm-{key}": value for key, value in farm.items()})
        return data

    def new_member(self, number="A-NEW1"):
        return Member.objects.filter(organisation=self.alpha, membership_number=number).first()

    def test_form_shows_member_and_farm_sections(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("member_create"))
        self.assertContains(response, "Member information")
        self.assertContains(response, "Farm details")
        self.assertContains(response, 'id="id_location"')
        self.assertContains(response, 'id="id_farm-location"')
        self.assertContains(response, 'id="id_farm-latitude"')
        self.assertContains(response, "Maize")
        self.assertNotContains(response, "Coffee")

    def test_member_only_still_works_and_creates_no_farm(self):
        self.login_as(self.admin)
        response = self.client.post(reverse("member_create"), self.payload())
        member = self.new_member()
        self.assertIsNotNone(member)
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        self.assertFalse(Farm.objects.filter(member=member).exists())

    def test_member_farm_and_crops_saved_together(self):
        self.login_as(self.admin)
        self.client.post(reverse("member_create"), self.payload(
            name="River plot", size="1.50", size_unit=Farm.SizeUnit.ACRES, location="Savelugu",
            latitude="9.624000", longitude="-0.825000", crops=[str(self.maize.pk), str(self.cocoa.pk)], season="2026 major",
        ))
        member = self.new_member()
        self.assertEqual(member.location, "Tamale town")
        farm = Farm.objects.get(member=member)
        self.assertEqual((farm.name, farm.location, farm.size_unit), ("River plot", "Savelugu", Farm.SizeUnit.ACRES))
        self.assertEqual(str(farm.latitude), "9.624000")
        seasons = FarmCropSeason.objects.filter(farm=farm)
        self.assertEqual(set(seasons.values_list("crop__name", flat=True)), {"Maize", "Cocoa"})
        self.assertEqual(set(seasons.values_list("season", flat=True)), {"2026 major"})
        self.assertEqual(MemberHistory.objects.filter(member=member, action=MemberHistory.Action.CREATED).count(), 1)

    def test_blank_farm_name_defaults_to_main_farm(self):
        self.login_as(self.admin)
        self.client.post(reverse("member_create"), self.payload(location="Savelugu"))
        self.assertEqual(Farm.objects.get(member=self.new_member()).name, "Main farm")

    def test_crops_without_season_save_nothing(self):
        self.login_as(self.admin)
        response = self.client.post(reverse("member_create"), self.payload(crops=[str(self.maize.pk)]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter the season for the selected crops.")
        self.assertIsNone(self.new_member())

    def test_half_entered_coordinates_save_nothing(self):
        self.login_as(self.admin)
        response = self.client.post(reverse("member_create"), self.payload(latitude="9.600000"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter both latitude and longitude")
        self.assertIsNone(self.new_member())

    def test_member_and_farm_errors_show_together(self):
        self.login_as(self.admin)
        response = self.client.post(reverse("member_create"), self.payload(number="A-F01", crops=[str(self.maize.pk)]))
        self.assertContains(response, "already exists")
        self.assertContains(response, "Enter the season for the selected crops.")

    def test_duplicate_membership_number_creates_no_farm(self):
        self.login_as(self.admin)
        farms_before = Farm.objects.count()
        response = self.client.post(reverse("member_create"), self.payload(number="a-f01", location="Savelugu"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Farm.objects.count(), farms_before)

    def test_crop_from_another_organisation_is_rejected(self):
        self.login_as(self.admin)
        response = self.client.post(reverse("member_create"), self.payload(crops=[str(self.beta_crop.pk)], season="2026"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.new_member())
        self.assertFalse(FarmCropSeason.objects.filter(crop=self.beta_crop, farm__organisation=self.alpha).exists())

    def test_field_officer_can_add_member_with_farm(self):
        self.login_as(self.field)
        response = self.client.post(reverse("field_member_create"), self.payload(
            number="A-NEW2", location="Yendi", crops=[str(self.maize.pk)], season="2026 minor",
        ))
        self.assertRedirects(response, reverse("field_home"), fetch_redirect_response=False)
        member = self.new_member("A-NEW2")
        farm = Farm.objects.get(member=member)
        self.assertEqual(farm.organisation, self.alpha)
        self.assertEqual(FarmCropSeason.objects.filter(farm=farm, crop=self.maize, season="2026 minor").count(), 1)
        self.assertEqual(MemberHistory.objects.filter(member=member, action=MemberHistory.Action.CREATED).count(), 1)

    def test_field_officer_form_shows_farm_section_only_on_add_member(self):
        self.login_as(self.field)
        self.assertContains(self.client.get(reverse("field_member_create")), 'id="id_farm-latitude"')

    def test_edit_member_has_no_farm_section(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("member_edit", args=[self.alpha_member.pk]))
        self.assertNotContains(response, "Farm details")
