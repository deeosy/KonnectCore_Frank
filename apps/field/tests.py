from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from apps.farms.models import Crop
from apps.groups.models import StructureUnit,GroupMemberAssignment
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation,OrganisationMembership
from .models import FieldVisit
U=get_user_model()
class FieldTests(TestCase):
 def setUp(self):
  self.a=Organisation.objects.create(name='A',slug='field-a');self.b=Organisation.objects.create(name='B',slug='field-b')
  self.f=U.objects.create_user(email='field@a.test',password='x');self.f2=U.objects.create_user(email='field2@a.test',password='x');self.admin=U.objects.create_user(email='admin@a.test',password='x');self.ob=U.objects.create_user(email='admin@b.test',password='x')
  self.fm=OrganisationMembership.objects.create(organisation=self.a,user=self.f,role='field_officer');self.fm2=OrganisationMembership.objects.create(organisation=self.a,user=self.f2,role='field_officer');OrganisationMembership.objects.create(organisation=self.a,user=self.admin,role='admin');OrganisationMembership.objects.create(organisation=self.b,user=self.ob,role='admin')
  self.m=Member.objects.create(organisation=self.a,created_by=self.admin,updated_by=self.admin,membership_number='A1',first_name='Ama',last_name='One');self.un=Member.objects.create(organisation=self.a,created_by=self.admin,updated_by=self.admin,membership_number='A2',first_name='Una',last_name='Two');self.mb=Member.objects.create(organisation=self.b,created_by=self.ob,updated_by=self.ob,membership_number='B1',first_name='Beta',last_name='One')
  g=StructureUnit.objects.create(organisation=self.a,name='G',unit_type='group',field_officer=self.fm);GroupMemberAssignment.objects.create(organisation=self.a,unit=g,member=self.m);self.crop=Crop.objects.create(organisation=self.a,name='Maize')
 def login(self,u):self.client.force_login(u);s=self.client.session;s[ActiveOrganisationMiddleware.SESSION_KEY]=self.a.pk;s.save()
 def test_assignment_scope(self):
  self.login(self.f);r=self.client.get(reverse('field_home'));self.assertContains(r,'Ama One');self.assertNotContains(r,'Una Two');self.assertNotContains(r,'Beta One')
  for name in ('field_visit_add','field_farm_update','field_collection_add'):self.assertEqual(self.client.get(reverse(name,args=[self.un.pk])).status_code,404)
 def test_field_records_visit_and_collection(self):
  self.login(self.f);r=self.client.post(reverse('field_visit_add',args=[self.m.pk]),{'visit_date':'2026-09-11','notes':'Healthy','latitude':'5','longitude':'-1'});self.assertRedirects(r,reverse('field_home'));self.assertEqual(FieldVisit.objects.get().recorded_by,self.f)
  r=self.client.post(reverse('field_collection_add',args=[self.m.pk]),{'member':self.m.pk,'crop':self.crop.pk,'quantity':'2','quantity_unit':'kg','collection_date':'2026-09-11','collection_location':'Farm','quality_grade':'A','price_per_unit':'3','notes':''});self.assertRedirects(r,reverse('field_home'));self.assertEqual(self.m.collection_records.get().recorded_by,self.f)
 def test_other_roles_cannot_use_field_mutations(self):
  self.login(self.admin);self.assertEqual(self.client.get(reverse('field_home')).status_code,200);self.assertEqual(self.client.get(reverse('field_member_create')).status_code,403)
 def test_cross_tenant_visit_rejected(self):
  self.login(self.f);self.assertEqual(self.client.get(reverse('field_visit_add',args=[self.mb.pk])).status_code,404)