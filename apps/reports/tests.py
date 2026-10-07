import csv,io
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from apps.collections.models import CollectionRecord
from apps.farms.models import Crop
from apps.finance.models import FinancialRecord
from apps.groups.models import StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation,OrganisationMembership
U=get_user_model()
class ReportTests(TestCase):
 def setUp(self):
  self.a=Organisation.objects.create(name='A',slug='report-a',currency='GHS');self.b=Organisation.objects.create(name='B',slug='report-b')
  self.u=U.objects.create_user(email='r@a.test',password='x');self.f=U.objects.create_user(email='rf@a.test',password='x');self.ub=U.objects.create_user(email='r@b.test',password='x')
  for o,u,r in ((self.a,self.u,'admin'),(self.a,self.f,'field_officer'),(self.b,self.ub,'admin')):OrganisationMembership.objects.create(organisation=o,user=u,role=r)
  self.m=Member.objects.create(organisation=self.a,created_by=self.u,updated_by=self.u,membership_number='A1',first_name='Alpha',last_name='Member');self.mb=Member.objects.create(organisation=self.b,created_by=self.ub,updated_by=self.ub,membership_number='B1',first_name='Secret',last_name='Member');self.ca=Crop.objects.create(organisation=self.a,name='Maize');self.cb=Crop.objects.create(organisation=self.b,name='Coffee');StructureUnit.objects.create(organisation=self.a,name='Group A',unit_type='group')
  CollectionRecord.objects.create(organisation=self.a,member=self.m,crop=self.ca,quantity=2,quantity_unit='kg',collection_date=date.today(),collection_location='A',price_per_unit=3,recorded_by=self.u);CollectionRecord.objects.create(organisation=self.b,member=self.mb,crop=self.cb,quantity=9,quantity_unit='kg',collection_date=date.today(),collection_location='B',price_per_unit=9,recorded_by=self.ub);FinancialRecord.objects.create(organisation=self.a,record_type='due',member=self.m,amount=10,paid_amount=4,payment_method='cash',status='part_paid',payment_date=date.today(),recorded_by=self.u)
 def login(self,u):self.client.force_login(u);s=self.client.session;s[ActiveOrganisationMiddleware.SESSION_KEY]=self.a.pk;s.save()
 def test_dashboard_and_reports_are_tenant_scoped(self):
  self.login(self.u);r=self.client.get(reverse('dashboard'));self.assertContains(r,'GHS\u00a04.00');self.assertContains(r,'GHS\u00a06.00');r=self.client.get(reverse('reports_home'));self.assertContains(r,'Alpha Member');self.assertNotContains(r,'Secret Member')
 def test_csv_and_xlsx_exports_are_tenant_scoped(self):
  self.login(self.u);r=self.client.get(reverse('export_report',args=['members','csv']));text=r.content.decode();self.assertIn('A1,Alpha,Member',text);self.assertNotIn('B1,Secret,Member',text)
  r=self.client.get(reverse('export_report',args=['collections','xlsx']));wb=load_workbook(io.BytesIO(r.content));values=' '.join(str(v) for row in wb.active.iter_rows(values_only=True) for v in row);self.assertIn('Alpha Member',values);self.assertNotIn('Secret Member',values)
 def test_field_officer_cannot_export(self):
  self.login(self.f);self.assertRedirects(self.client.get(reverse('reports_home')),reverse('field_home'),fetch_redirect_response=False);self.assertEqual(self.client.get(reverse('export_report',args=['members','csv'])).status_code,403)
 def test_invalid_export_is_404(self):
  self.login(self.u);self.assertEqual(self.client.get(reverse('export_report',args=['bad','csv'])).status_code,404)