from django.urls import path

from . import views

urlpatterns = [
    path("", views.collection_list, name="collection_list"),
    path("record/", views.collection_create, name="collection_create"),
    path("<uuid:record_id>/", views.collection_detail, name="collection_detail"),
    path("<uuid:record_id>/edit/", views.collection_edit, name="collection_edit"),
    path("<uuid:record_id>/photo/", views.collection_photo, name="collection_photo"),
]