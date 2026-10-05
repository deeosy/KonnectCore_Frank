from django.urls import path

from . import views

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("register/", views.member_create, name="member_create"),
    path("import/", views.member_import, name="member_import"),
    path("<uuid:member_id>/", views.member_detail, name="member_detail"),
    path("<uuid:member_id>/edit/", views.member_edit, name="member_edit"),
    path("<uuid:member_id>/archive/", views.member_archive, name="member_archive"),
    path("<uuid:member_id>/documents/add/", views.member_document_add, name="member_document_add"),
    path("<uuid:member_id>/photo/", views.member_photo, name="member_photo"),
    path("documents/<uuid:document_id>/download/", views.member_document_download, name="member_document_download"),
]
