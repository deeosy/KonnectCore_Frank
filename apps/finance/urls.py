from django.urls import path
from . import views
urlpatterns=[path("",views.finance_list,name="finance_list"),path("record/",views.finance_create,name="finance_create"),path("<uuid:record_id>/",views.finance_detail,name="finance_detail"),path("<uuid:record_id>/edit/",views.finance_edit,name="finance_edit")]