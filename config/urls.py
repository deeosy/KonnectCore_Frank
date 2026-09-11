from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.organisations import views
from apps.organisations.forms import LoginForm

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.entrypoint, name="entrypoint"),
    path("organisations/choose/", views.choose_organisation, name="choose_organisation"),
    path("workspace/", views.workspace, name="workspace"),
    path("workspace/members/", include("apps.members.urls")),
    path("workspace/structure/", include("apps.groups.urls")),
    path("workspace/farms/", include("apps.farms.urls")),
    path("workspace/staff/", views.staff_list, name="staff_list"),
    path("workspace/staff/create/", views.staff_create, name="staff_create"),
    path("workspace/staff/invite/", views.staff_invite, name="staff_invite"),
    path("invitations/<str:token>/accept/", views.accept_invitation, name="accept_invitation"),
    path("platform/organisations/", views.platform_organisations, name="platform_organisations"),
    path("platform/organisations/create/", views.platform_organisation_create, name="platform_organisation_create"),
]
