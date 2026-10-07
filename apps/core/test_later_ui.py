"""'Later' UI items from the 7 Oct 2026 UI review.

1. Menu and top-bar icons are inline SVG, hidden from screen readers, not text symbols.
2. The avatar shows the user's initials, falling back to the email's first letter.
3. 'Archive member' is a quiet link, not a button styled like 'Edit member'.
4. The Field Workspace intro for Admins/Managers is short.
5. Search placeholders fit a 360 px phone (20 characters or fewer).
6. Menu, close and sign-out buttons have a 44 x 44 px tap area.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

User = get_user_model()
BASE = Path(settings.BASE_DIR)
CSS = BASE / "static" / "css" / "app.css"
TEMPLATES = BASE / "templates"
TEXT_ICONS = "\u25ce\u25a6\u2318\u25c7\u21e3\u00a4\u2316\u2261\u2699\uff0b\u2197\u2630\u00d7"


def read(path):
    return path.read_text(encoding="utf-8")


class SignedInFixture(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Alpha Cooperative", slug="alpha", currency="GHS")
        self.admin = User.objects.create_user(email="fkmedia@alpha.test", password="CorrectHorse!42", first_name="Kay", last_name="Mark")
        OrganisationMembership.objects.create(organisation=self.org, user=self.admin, role=OrganisationMembership.Role.ADMIN)

    def login_as(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()


class SvgIconTests(SignedInFixture):
    def test_base_template_has_no_text_symbol_icons(self):
        html = read(TEMPLATES / "base.html")
        found = sorted({c for c in html if c in TEXT_ICONS})
        self.assertEqual(found, [], f"Text symbols still used as icons: {found}")

    def test_rendered_icons_are_svg_and_hidden_from_screen_readers(self):
        self.login_as(self.admin)
        html = self.client.get(reverse("staff_list")).content.decode()
        nav_icons = re.findall(r'<span class="nav-icon"[^>]*>(.*?)</span>', html, re.S)
        self.assertGreaterEqual(len(nav_icons), 8)
        for icon in nav_icons:
            self.assertIn("<svg", icon)
        svgs = re.findall(r"<svg\b[^>]*>", html)
        self.assertTrue(svgs)
        for tag in svgs:
            self.assertIn('aria-hidden="true"', tag)
            self.assertIn('focusable="false"', tag)

    def test_icon_only_controls_keep_accessible_names(self):
        self.login_as(self.admin)
        html = self.client.get(reverse("staff_list")).content.decode()
        for name in ("Open navigation", "Close navigation", "Sign out"):
            self.assertIn(f'aria-label="{name}"', html)


class AvatarTests(SignedInFixture):
    def avatars(self):
        html = self.client.get(reverse("staff_list")).content.decode()
        return re.findall(r'<span class="user-avatar"[^>]*>\s*([^<]*?)\s*</span>', html)

    def test_avatar_shows_initials_from_name(self):
        self.login_as(self.admin)
        values = self.avatars()
        self.assertTrue(values)
        self.assertEqual(set(values), {"KM"})

    def test_avatar_falls_back_to_email_letter_without_name(self):
        user = User.objects.create_user(email="zed@alpha.test", password="CorrectHorse!42")
        OrganisationMembership.objects.create(organisation=self.org, user=user, role=OrganisationMembership.Role.ADMIN)
        self.login_as(user)
        self.assertEqual(set(self.avatars()), {"Z"})

    def test_avatar_with_first_name_only(self):
        self.admin.last_name = ""
        self.admin.save()
        self.login_as(self.admin)
        self.assertEqual(set(self.avatars()), {"K"})


class ArchiveMemberLinkTests(TestCase):
    def test_archive_is_a_quiet_link_not_a_button(self):
        html = read(TEMPLATES / "members" / "member_detail.html")
        tags = re.findall(r"<a\b[^>]*member_archive[^>]*>", html)
        self.assertEqual(len(tags), 1)
        classes = re.search(r'class="([^"]*)"', tags[0]).group(1).split()
        self.assertNotIn("button", classes)
        self.assertIn("link-quiet", classes)

    def test_quiet_link_style_exists(self):
        self.assertRegex(read(CSS), r"\.link-quiet\s*\{")


class FieldIntroTests(TestCase):
    def test_admin_manager_field_intro_is_short(self):
        html = read(TEMPLATES / "field" / "home.html")
        match = re.search(r"All members \(field view\)</h1><p class=\"muted\">(.*?)</p>", html, re.S)
        self.assertIsNotNone(match)
        text = re.sub(r"\{\{.*?\}\}", "Manager", match.group(1))
        self.assertLessEqual(len(text), 80, text)
        self.assertNotIn("Field officers record", text)


class SearchPlaceholderTests(TestCase):
    def test_placeholders_fit_a_phone(self):
        too_long = []
        for path in TEMPLATES.rglob("*.html"):
            for value in re.findall(r'placeholder="([^"]+)"', read(path)):
                if len(value) > 20:
                    too_long.append(f"{path.relative_to(TEMPLATES)}: {value}")
        self.assertEqual(too_long, [])


class TapTargetTests(TestCase):
    def declarations_for(self, selector):
        decls = ""
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", read(CSS)):
            names = [s.strip() for s in selectors.split(",")]
            if selector in names:
                decls += body.replace(" ", "") + ";"
        return decls

    def test_icon_controls_are_at_least_44px(self):
        for selector in (".menu-button", ".icon-button", ".nav-close"):
            decls = self.declarations_for(selector)
            self.assertIn("min-width:44px", decls, selector)
            self.assertIn("min-height:44px", decls, selector)
