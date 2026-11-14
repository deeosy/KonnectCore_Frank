from django.urls import path
from . import views
urlpatterns=[
    path('',views.home,name='field_home'),
    path('members/register/',views.register_member,name='field_member_create'),
    path('members/<uuid:member_id>/',views.member_detail,name='field_member_detail'),
    path('members/<uuid:member_id>/visit/',views.visit_add,name='field_visit_add'),
    path('members/<uuid:member_id>/farm/',views.farm_update,name='field_farm_update'),
    path('members/<uuid:member_id>/collection/',views.collection_add,name='field_collection_add'),
    path('activity/',views.activity_workspace,name='field_activity'),
    path('visits/<uuid:visit_id>/photo/',views.visit_photo,name='field_visit_photo'),
    path('advisories/<int:advisory_id>/photo/',views.advisory_photo,name='field_advisory_photo'),
    path('advisories/',views.advisory_review_list,name='field_advisory_review_list'),
    path('advisories/<int:advisory_id>/',views.advisory_review_detail,name='field_advisory_review_detail')
]
