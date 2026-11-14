from django.urls import path
from . import views

urlpatterns = [
    path("", views.input_allocation_list, name="input_allocation_list"),
    path("audit/", views.distribution_audit, name="input_distribution_audit"),
    path("<uuid:pk>/", views.input_allocation_detail, name="input_allocation_detail"),
    path("create/", views.input_allocation_create, name="input_allocation_create"),
]
