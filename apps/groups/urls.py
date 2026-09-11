from django.urls import path

from . import views

urlpatterns = [
    path("", views.structure_list, name="structure_list"),
    path("create/", views.structure_create, name="structure_create"),
    path("<uuid:unit_id>/", views.structure_detail, name="structure_detail"),
    path("<uuid:unit_id>/edit/", views.structure_edit, name="structure_edit"),
    path("<uuid:unit_id>/members/add/", views.assignment_add, name="assignment_add"),
    path(
        "<uuid:unit_id>/members/<uuid:assignment_id>/remove/",
        views.assignment_remove,
        name="assignment_remove",
    ),
]
