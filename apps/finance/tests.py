from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation,OrganisationMembership
from .forms import FinancialRecordForm
from .models import FinancialRecord
User=get_user_model()
class FinanceTests(TestCase):
 def setUp(self):
  self.a=Organisation.objects.create(name="Alpha",slug="fin-alpha");self.b=Organisation.objects.create(name="Beta",slug="fin-beta")
  self.admin=User.objects.create_user(email="fa@x.test",password="x");self.field=User.objects.create_user(email="ff@x.test",password="x");self.other=User.objects.create_user(email="fb@x.test",password="x")
  for o,u,r in ((self.a,self.admin,"admin"),(self.a,self.field,"field_officer"),(self.b,self.other,"admin")):OrganisationMembership.objects.create(organisation=o,user=u,role=r)
  self.ma=Member.objects.create(organisation=self.a,created_by=self.admin,updated_by=self.admin,membership_number="A",first_name="Ama",last_name="A")
  self.mb=Member.objects.create(organisation=self.b,created_by=self.other,updated_by=self.other,membership_number="B",first_name="Ben",last_name="B")
  self.item=FinancialRecord.objects.create(organisation=self.a,record_type="due",member=self.ma,amount=100,paid_amount=25,payment_method="cash",status="part_paid",payment_date=date.today(),recorded_by=self.admin)
 def login(self,u,o=None):
  self.client.force_login(u);s=self.client.session;s[ActiveOrganisationMiddleware.SESSION_KEY]=(o or self.a).pk;s.save()
 def data(self,**x):
  d={"record_type":"due","member":str(self.ma.pk),"amount":"80","paid_amount":"80","payment_method":"cash","status":"paid","payment_date":"2026-09-11","reference_number":"R1","notes":""};d.update(x);return d
 def test_isolation_and_roles(self):
  foreign=FinancialRecord.objects.create(organisation=self.b,record_type="due",member=self.mb,amount=10,paid_amount=0,payment_method="cash",status="pending",payment_date=date.today(),recorded_by=self.other)
  self.login(self.admin);self.assertNotContains(self.client.get(reverse("finance_list")),"Ben B");self.assertEqual(self.client.get(reverse("finance_detail",args=[foreign.pk])).status_code,404)
  self.client.logout();self.login(self.field);self.assertEqual(self.client.get(reverse("finance_list")).status_code,200);self.assertEqual(self.client.get(reverse("finance_create")).status_code,403)
 def test_create_and_member_history(self):
  self.login(self.admin);r=self.client.post(reverse("finance_create"),self.data());obj=FinancialRecord.objects.exclude(pk=self.item.pk).get();self.assertRedirects(r,reverse("finance_detail",args=[obj.pk]));self.assertEqual(obj.recorded_by,self.admin);self.assertEqual(obj.outstanding_amount,Decimal("0.00"));self.assertContains(self.client.get(reverse("member_detail",args=[self.ma.pk])),"Payments and dues history")
 def test_tenant_choices_and_validation(self):
  f=FinancialRecordForm(organisation=self.a,recorded_by=self.admin);self.assertIn(self.ma,f.fields["member"].queryset);self.assertNotIn(self.mb,f.fields["member"].queryset)
  self.login(self.admin);r=self.client.post(reverse("finance_create"),self.data(member=str(self.mb.pk)));self.assertIn("Select a valid choice. That choice is not one of the available choices.", r.context["form"].errors["member"])
  bad=FinancialRecord(organisation=self.a,record_type="expense",member=self.ma,amount=10,paid_amount=0,payment_method="cash",status="pending",payment_date=date.today(),recorded_by=self.admin)
  with self.assertRaises(ValidationError):bad.full_clean()
 def test_outstanding_cancelled(self):
  self.item.status="cancelled";self.assertEqual(self.item.outstanding_amount,Decimal("0.00"))