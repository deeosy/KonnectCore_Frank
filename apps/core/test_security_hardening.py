import importlib

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import clear_url_caches

import config.urls


def _reload_urls():
    clear_url_caches()
    importlib.reload(config.urls)
    clear_url_caches()


class SignedInPagesNotStoredTests(TestCase):
    """Browsers must not keep copies of signed-in pages (Back after sign-out, shared phones)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="cache_check@example.test", password="Strong-Test-Pass-9182"
        )

    def test_signed_in_response_is_marked_no_store(self):
        self.client.force_login(self.user)
        response = self.client.get("/workspace/")
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache_control)
        self.assertIn("private", cache_control)
        self.assertIn("Cookie", response.headers.get("Vary", ""))

    def test_after_logout_private_page_requires_login(self):
        self.client.force_login(self.user)
        self.client.post("/logout/")
        response = self.client.get("/workspace/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.headers["Location"])


class DjangoAdminSwitchTests(TestCase):
    """Django's built-in admin bypasses organisation privacy rules; it must be switchable off."""

    def setUp(self):
        self.addCleanup(_reload_urls)

    @override_settings(DJANGO_ADMIN_ENABLED=False)
    def test_admin_not_routed_when_disabled(self):
        _reload_urls()
        self.assertEqual(self.client.get("/django-admin/").status_code, 404)
        self.assertEqual(self.client.get("/django-admin/login/").status_code, 404)

    @override_settings(DJANGO_ADMIN_ENABLED=True)
    def test_admin_routed_when_enabled(self):
        _reload_urls()
        response = self.client.get("/django-admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/django-admin/login/", response.headers["Location"])