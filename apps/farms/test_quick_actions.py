"""Phase 1 of Kennedy's feedback: Add Crop farm picker, mobile quick-action bar, location button, wording."""
import re

from django.urls import reverse

from .forms import FarmForm
from .tests import FarmFixture


def quick_actions(response):
    """Return only the quick-action bar markup, or '' when the bar is absent."""
    match = re.search(r'<nav class="quick-actions".*?</nav>', response.content.decode(), re.S)
    return match.group(0) if match else ""


class SeasonPickFarmTests(FarmFixture):
    def test_admin_and_manager_can_open_the_picker(self):
        for user in (self.admin, self.manager):
            self.login_as(user)
            response = self.client.get(reverse("season_pick_farm"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "North field")
            self.assertContains(response, reverse("season_create", args=[self.alpha_farm.pk]))

    def test_field_officer_is_refused(self):
        self.login_as(self.field)
        self.assertEqual(self.client.get(reverse("season_pick_farm")).status_code, 403)

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(reverse("season_pick_farm"))
        self.assertEqual(response.status_code, 302)

    def test_picker_does_not_leak_other_organisations(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("season_pick_farm"))
        self.assertNotContains(response, "Rift farm")
        self.assertNotContains(response, str(self.beta_farm.pk))
        response = self.client.get(reverse("season_pick_farm"), {"q": "Nakuru"})
        self.assertContains(response, "No farms match this search.")
        self.assertNotContains(response, "Rift farm")

    def test_search_matches_member_and_farm(self):
        self.login_as(self.admin)
        for query in ("Mensah", "A-F01", "North", "Tamale"):
            self.assertContains(self.client.get(reverse("season_pick_farm"), {"q": query}), "North field")
        self.assertContains(self.client.get(reverse("season_pick_farm"), {"q": "nothing-like-this"}), "No farms match this search.")


class QuickActionBarTests(FarmFixture):
    def test_admin_bar_links_to_manager_actions_and_home(self):
        self.login_as(self.admin)
        bar = quick_actions(self.client.get(reverse("farm_list")))
        self.assertTrue(bar)
        for name in ("member_create", "collection_create", "season_pick_farm", "dashboard"):
            self.assertIn(f'href="{reverse(name)}"', bar)
        self.assertNotIn(reverse("staff_list"), bar)

    def test_field_officer_bar_only_links_to_allowed_pages(self):
        self.login_as(self.field)
        bar = quick_actions(self.client.get(reverse("field_home")))
        self.assertTrue(bar)
        self.assertIn(f'href="{reverse("field_member_create")}"', bar)
        self.assertIn(f'href="{reverse("field_home")}"', bar)
        for name in ("member_create", "collection_create", "season_pick_farm", "dashboard"):
            self.assertNotIn(f'href="{reverse(name)}"', bar)

    def test_every_bar_link_opens_for_its_role(self):
        for user, start in ((self.admin, "farm_list"), (self.manager, "farm_list"), (self.field, "field_home")):
            self.login_as(user)
            bar = quick_actions(self.client.get(reverse(start)))
            links = re.findall(r'href="([^"]+)"', bar)
            self.assertTrue(links)
            for url in links:
                status = self.client.get(url).status_code
                self.assertIn(status, (200, 302), f"{user.email} -> {url} returned {status}")
                self.assertNotEqual(status, 403)

    def test_current_page_is_marked_active(self):
        self.login_as(self.admin)
        bar = quick_actions(self.client.get(reverse("season_pick_farm")))
        self.assertRegex(bar, r'class="qa-item active" href="' + re.escape(reverse("season_pick_farm")) + r'" aria-current="page"')
        self.assertEqual(bar.count('aria-current="page"'), 1)

    def test_signed_out_pages_have_no_bar(self):
        self.assertEqual(quick_actions(self.client.get(reverse("login"))), "")


class LocationAndWordingTests(FarmFixture):
    def test_map_coordinates_are_submitted_as_hidden_farm_fields(self):
        form = FarmForm(organisation=self.alpha)
        self.assertEqual(form.fields["latitude"].widget.input_type, "hidden")
        self.assertEqual(form.fields["longitude"].widget.input_type, "hidden")

    def test_location_script_is_loaded_with_the_csp_nonce(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("farm_create"))
        html = response.content.decode()
        match = re.search(r'<script src="[^"]*js/farm_location\.js" nonce="([^"]+)" defer></script>', html)
        self.assertIsNotNone(match)
        self.assertIn(f"'nonce-{match.group(1)}'", response.headers["Content-Security-Policy"])
        self.assertContains(response, 'id="id_latitude"')
        self.assertContains(response, 'id="id_longitude"')

    def test_register_wording_is_replaced_by_add(self):
        self.login_as(self.admin)
        for name in ("member_list", "farm_list", "member_create", "farm_create"):
            response = self.client.get(reverse(name))
            self.assertNotContains(response, "Register member")
            self.assertNotContains(response, "Register farm")
        self.assertContains(self.client.get(reverse("member_list")), "Add member")
        self.assertContains(self.client.get(reverse("farm_list")), "Add farm")

    def test_sidebar_follows_suggested_priority_order(self):
        self.login_as(self.admin)
        html = self.client.get(reverse("farm_list")).content.decode()
        nav = re.search(r'<nav class="sidebar-nav">.*?</nav>', html, re.S).group(0)
        order = [reverse(n) for n in ("dashboard", "member_list", "collection_list", "finance_list", "farm_list", "structure_list")]
        positions = [nav.index(f'href="{url}"') for url in order]
        self.assertEqual(positions, sorted(positions))
