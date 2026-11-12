from django import forms
from .models import InputAllocation

class InputAllocationForm(forms.ModelForm):
    class Meta:
        model = InputAllocation
        fields = ["member", "input_type", "quantity"]

    def __init__(self, *args, organisation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organisation:
            self.fields["member"].queryset = self.fields["member"].queryset.filter(organisation=organisation)

class InputAllocationStatusForm(forms.ModelForm):
    class Meta:
        model = InputAllocation
        fields = ["status"]
