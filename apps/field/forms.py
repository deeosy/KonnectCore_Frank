from django import forms
from .models import AdvisoryRecord

class AdvisoryRecordForm(forms.ModelForm):
    class Meta:
        model = AdvisoryRecord
        fields = ["observation", "photo"]
