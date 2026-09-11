from django import forms
from apps.members.forms import MemberForm
from apps.farms.forms import FarmForm
from apps.collections.forms import CollectionRecordForm
from .models import FieldVisit
class FieldVisitForm(forms.ModelForm):
 class Meta:
  model=FieldVisit;fields=["visit_date","notes","latitude","longitude","photo"]
  widgets={"visit_date":forms.DateInput(attrs={"type":"date"}),"notes":forms.Textarea(attrs={"rows":4}),"latitude":forms.NumberInput(attrs={"step":"0.000001"}),"longitude":forms.NumberInput(attrs={"step":"0.000001"})}
 def __init__(self,*a,organisation,member,recorded_by,**k):
  self.organisation=organisation;self.member=member;self.recorded_by=recorded_by;super().__init__(*a,**k);self.instance.organisation=organisation;self.instance.member=member;self.instance.recorded_by=recorded_by
 def save(self,commit=True):
  x=super().save(False);x.organisation=self.organisation;x.member=self.member;x.recorded_by=self.recorded_by;x.full_clean()
  if commit:x.save()
  return x