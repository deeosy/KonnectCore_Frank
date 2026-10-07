import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

NONCE_RE = re.compile(r"'nonce-([A-Za-z0-9_\-+/=]+)'")


class ContentSecurityPolicyTests(TestCase):
    def policy(self, response):
        value = response.headers.get("Content-Security-Policy", "")
        self.assertTrue(value, "Content-Security-Policy header missing")
        return value

    def test_policy_restricts_scripts_framing_and_plugins(self):
        policy = self.policy(self.client.get("/login/"))
        self.assertIn("default-src 'self'", policy)
        self.assertRegex(policy, r"script-src 'self' 'nonce-")
        self.assertNotIn("'unsafe-inline'", policy.split("script-src", 1)[1].split(";", 1)[0])
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("base-uri 'self'", policy)
        self.assertIn("form-action 'self'", policy)

    def test_every_script_tag_carries_the_page_nonce(self):
        response = self.client.get("/login/")
        nonce = NONCE_RE.search(self.policy(response)).group(1)
        html = response.content.decode()
        tags = re.findall(r"<script\b[^>]*>", html)
        self.assertTrue(tags)
        for tag in tags:
            self.assertIn('nonce="%s"' % nonce, tag)

    def test_nonce_changes_on_every_request(self):
        first = NONCE_RE.search(self.policy(self.client.get("/login/"))).group(1)
        second = NONCE_RE.search(self.policy(self.client.get("/login/"))).group(1)
        self.assertNotEqual(first, second)

    def test_signed_in_pages_also_get_the_policy(self):
        user = get_user_model().objects.create_user(email="csp_check@example.test", password="Strong-Test-Pass-6612")
        self.client.force_login(user)
        self.policy(self.client.get("/workspace/", follow=True))


class NoInlineEventHandlerTests(TestCase):
    """Inline handlers such as onsubmit= are blocked by the policy, so templates must not use them."""

    def test_templates_have_no_inline_event_handlers(self):
        roots = [Path(settings.BASE_DIR) / "templates", Path(settings.BASE_DIR) / "apps"]
        offenders = []
        for root in roots:
            for path in root.rglob("*.html"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"\son[a-z]+\s*=\s*[\"']", text):
                    offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(offenders, [])