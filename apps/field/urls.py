from django.urls import path
from . import views
urlpatterns=[path('',views.home,name='field_home'),path('members/register/',views.register_member,name='field_member_create'),path('members/<uuid:member_id>/',views.member_detail,name='field_member_detail'),path('members/<uuid:member_id>/visit/',views.visit_add,name='field_visit_add'),path('members/<uuid:member_id>/farm/',views.farm_update,name='field_farm_update'),path('members/<uuid:member_id>/collection/',views.collection_add,name='field_collection_add'),path('visits/<uuid:visit_id>/photo/',views.visit_photo,name='field_visit_photo')]
