from django.urls import path

from . import views

urlpatterns = [
    path("", views.farm_list, name="farm_list"),
    path("register/", views.farm_create, name="farm_create"),
    path("seasons/add/", views.season_pick_farm, name="season_pick_farm"),
    path("crops/", views.crop_list, name="crop_list"),
    path("crops/add/", views.crop_create, name="crop_create"),
    path("crops/<uuid:crop_id>/edit/", views.crop_edit, name="crop_edit"),
    path("<uuid:farm_id>/", views.farm_detail, name="farm_detail"),
    path("<uuid:farm_id>/edit/", views.farm_edit, name="farm_edit"),
    path("<uuid:farm_id>/seasons/add/", views.season_create, name="season_create"),
    path("<uuid:farm_id>/seasons/<uuid:season_id>/edit/", views.season_edit, name="season_edit"),
]