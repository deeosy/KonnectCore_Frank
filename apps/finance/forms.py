from django import forms
from apps.members.models import Member
from .models import FinancialRecord

class FinancialRecordForm(forms.ModelForm):
    class Meta:
        model = FinancialRecord
        fields = ["record_type", "member", "amount", "paid_amount", "payment_method", "status", "payment_date", "reference_number", "notes"]
        widgets = {"payment_date": forms.DateInput(attrs={"type":"date"}), "notes": forms.Textarea(attrs={"rows":3})}
    def __init__(self,*args,organisation,recorded_by,**kwargs):
        self.organisation=organisation; self.recorded_by=recorded_by
        super().__init__(*args,**kwargs)
        self.instance.organisation=organisation
        if self.instance._state.adding: self.instance.recorded_by=recorded_by
        self.fields["member"].queryset=Member.objects.for_organisation(organisation)
    def save(self,commit=True):
        item=super().save(commit=False); item.organisation=self.organisation
        if item._state.adding: item.recorded_by=self.recorded_by
        item.full_clean()
        if commit: item.save()
        return item