"""Friendly error pages render without technical details (UAT issue I-3)."""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views import defaults

TECHNICAL_MARKERS = ("Traceback", "Exception Value", "settings.py", "DEBUG = True")


@override_settings(DEBUG=False)
class ErrorPageTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/some/path/")

    def assert_friendly(self, response, status, heading):
        self.assertEqual(response.status_code, status)
        body = response.content.decode()
        self.assertIn(heading, body)
        self.assertIn("Return to workspace", body)
        for marker in TECHNICAL_MARKERS:
            self.assertNotIn(marker, body)

    def test_500_page(self):
        self.assert_friendly(defaults.server_error(self.request), 500, "Something went wrong")

    def test_404_page(self):
        response = defaults.page_not_found(self.request, Http404("internal detail"))
        self.assert_friendly(response, 404, "Page not found")
        self.assertNotIn("internal detail", response.content.decode())

    def test_403_page(self):
        response = defaults.permission_denied(self.request, PermissionDenied("internal detail"))
        self.assert_friendly(response, 403, "Access not allowed")
        self.assertNotIn("internal detail", response.content.decode())
