"""Search engine and browser icon files: only the sign-in page may be indexed."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.views import PRIVATE_PREFIXES


class RobotsAndSitemapTests(TestCase):
    def test_robots_blocks_every_private_area_and_links_the_sitemap(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        body = response.content.decode()
        for prefix in ("/workspace/", "/field/", "/platform/", "/invitations/", "/password-reset/"):
            self.assertIn("Disallow: %s" % prefix, body)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", body)
        self.assertNotIn("Disallow: /\n", body)

    def test_sitemap_lists_only_the_sign_in_page(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertEqual(body.count("<loc>"), 1)
        self.assertIn("<loc>http://testserver/login/</loc>", body)
        for prefix in PRIVATE_PREFIXES:
            self.assertNotIn(prefix, body)


class IconTests(TestCase):
    def test_favicon_ico_redirects_to_the_static_icon(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 302)
        self.assertIn("img/favicon", response["Location"])

    def test_manifest_lists_app_icons(self):
        response = self.client.get("/site.webmanifest")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["name"], "KonnectCore")
        self.assertEqual({icon["sizes"] for icon in data["icons"]}, {"192x192", "512x512"})


class MetaRobotsTests(TestCase):
    def test_sign_in_page_is_indexable_with_canonical_and_share_tags(self):
        html = self.client.get("/login/").content.decode()
        self.assertIn('<meta name="robots" content="index, follow">', html)
        self.assertIn('<link rel="canonical" href="http://testserver/login/">', html)
        self.assertIn('<meta name="description"', html)
        self.assertIn('property="og:image"', html)
        self.assertIn('rel="icon"', html)
        self.assertNotIn("noindex", html)

    def test_signed_in_pages_are_not_indexed(self):
        user = get_user_model().objects.create_user(email="seo_check@example.test", password="Strong-Test-Pass-7731")
        self.client.force_login(user)
        response = self.client.get("/workspace/", follow=True)
        html = response.content.decode()
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        self.assertNotIn('rel="canonical"', html)
