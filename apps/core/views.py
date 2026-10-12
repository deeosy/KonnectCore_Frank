"""Public, sign-in-free files for search engines and browsers.

Only the sign-in page is meant to appear in search results. Workspaces,
platform pages and one-time links (invitations, password resets) are private,
so robots.txt blocks them and base.html marks every page noindex unless a
template opts in.
"""
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

PRIVATE_PREFIXES = (
    "/workspace/",
    "/field/",
    "/platform/",
    "/organisations/",
    "/invitations/",
    "/password-reset/",
    "/logout/",
    "/django-admin/",
    "/media/",
)


@require_GET
@cache_control(public=True, max_age=86400)
def robots_txt(request):
    lines = ["User-agent: *"]
    lines += ["Disallow: %s" % prefix for prefix in PRIVATE_PREFIXES]
    lines.append("Sitemap: %s" % request.build_absolute_uri(reverse("sitemap_xml")))
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


@require_GET
@cache_control(public=True, max_age=86400)
def sitemap_xml(request):
    login_url = request.build_absolute_uri(reverse("login"))
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url><loc>%s</loc></url>\n"
        "</urlset>\n" % login_url
    )
    return HttpResponse(body, content_type="application/xml; charset=utf-8")


@require_GET
@cache_control(public=True, max_age=86400)
def favicon_ico(request):
    # Browsers ask for /favicon.ico directly; send them to the hashed static file.
    return redirect(staticfiles_storage.url("img/favicon.ico"))


@require_GET
@cache_control(public=True, max_age=86400)
def web_manifest(request):
    manifest = {
        "name": "KonnectCore",
        "short_name": "KonnectCore",
        "description": "Secure workspace for cooperatives: members, farms, collections, payments and field operations.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#131e25",
        "icons": [
            {"src": staticfiles_storage.url("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": staticfiles_storage.url("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
        ],
    }
    return JsonResponse(manifest, content_type="application/manifest+json")
