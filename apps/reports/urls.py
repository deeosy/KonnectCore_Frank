from django.urls import path
from . import views
urlpatterns=[path('dashboard/',views.dashboard,name='dashboard'),path('',views.reports_home,name='reports_home'),path('export/<str:report>/<str:format>/',views.export_report,name='export_report')]
