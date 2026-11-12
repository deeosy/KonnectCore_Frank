from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views
from apps.organisations import views

urlpatterns = [
    path("login/", views.RoleAwareLoginView.as_view(), name="login"),
    path("logout/", views.auth_views.LogoutView.as_view(), name="logout"),
    path("", views.entrypoint, name="entrypoint"),
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    path("sitemap.xml", core_views.sitemap_xml, name="sitemap_xml"),
    path("favicon.ico", core_views.favicon_ico, name="favicon_ico"),
    path("site.webmanifest", core_views.web_manifest, name="web_manifest"),
    path("organisations/choose/", views.choose_organisation, name="choose_organisation"),
    path("workspace/", views.workspace, name="workspace"),
    path("workspace/members/", include("apps.members.urls")),
    path("workspace/structure/", include("apps.groups.urls")),
    path("workspace/farms/", include("apps.farms.urls")),
    path("workspace/collections/", include("apps.collections.urls")),
    path("workspace/finance/", include("apps.finance.urls")),
    path("field/", include("apps.field.urls")),
    path("workspace/reports/", include("apps.reports.urls")),
    path("workspace/inputs/", include("apps.inputs.urls")),
    path("workspace/staff/", views.staff_list, name="staff_list"),
    path("workspace/staff/create/", views.staff_create, name="staff_create"),
    path("workspace/staff/invite/", views.staff_invite, name="staff_invite"),
    path("workspace/staff/invitations/<int:invitation_id>/cancel/", views.staff_invitation_cancel, name="staff_invitation_cancel"),
    path("workspace/staff/<int:membership_id>/reset-password/", views.staff_password_reset, name="staff_password_reset"),
    path("invitations/<str:token>/accept/", views.accept_invitation, name="accept_invitation"),
    path("password-reset/<str:token>/", views.password_reset_accept, name="password_reset_accept"),
    path("platform/organisations/", views.platform_organisations, name="platform_organisations"),
    path("platform/organisations/create/", views.platform_organisation_create, name="platform_organisation_create"),
    path("platform/organisations/<int:organisation_id>/", views.platform_organisation_detail, name="platform_organisation_detail"),
]

# Off on the hosted server: Django admin bypasses organisation privacy rules (see settings).
if settings.DJANGO_ADMIN_ENABLED:
    urlpatterns.insert(0, path("django-admin/", admin.site.urls))
