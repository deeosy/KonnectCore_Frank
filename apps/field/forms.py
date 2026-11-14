from django import forms
from apps.core.submissions import add_submission_key
from .models import FieldVisit, AdvisoryRecord

class FieldVisitForm(forms.ModelForm):
 class Meta:
  model=FieldVisit;fields=["visit_date","notes","latitude","longitude","photo"]
  widgets={"visit_date":forms.DateInput(attrs={"type":"date"}),"notes":forms.Textarea(attrs={"rows":4}),"latitude":forms.NumberInput(attrs={"step":"0.000001"}),"longitude":forms.NumberInput(attrs={"step":"0.000001"})}
 def __init__(self,*a,organisation,member,recorded_by,**k):
  self.organisation=organisation;self.member=member;self.recorded_by=recorded_by;super().__init__(*a,**k);self.instance.organisation=organisation;self.instance.member=member;self.instance.recorded_by=recorded_by
  add_submission_key(self)
 def save(self,commit=True):
  x=super().save(False);x.organisation=self.organisation;x.member=self.member;x.recorded_by=self.recorded_by;x.full_clean()
  if commit:x.save()
  return x

class AdvisoryRecordForm(forms.ModelForm):
    observation = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    class Meta:
        model = AdvisoryRecord
        fields = ["observation", "photo"]

class AdvisoryReviewForm(forms.ModelForm):
    class Meta:
        model = AdvisoryRecord
        fields = ["review_comment"]
        widgets = {"review_comment": forms.Textarea(attrs={"rows": 4})}
