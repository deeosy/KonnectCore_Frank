from django import forms

from apps.members.models import Member

from .models import InputAllocation


class InputAllocationForm(forms.ModelForm):
    class Meta:
        model = InputAllocation
        fields = ["member", "input_type", "quantity"]

    def __init__(self, *args, organisation=None, member_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if member_queryset is not None:
            self.fields["member"].queryset = member_queryset
        elif organisation:
            self.fields["member"].queryset = Member.objects.for_organisation(organisation)


class InputAllocationStatusForm(forms.ModelForm):
    class Meta:
        model = InputAllocation
        fields = ["status"]
        labels = {"status": "New status"}

    def clean_status(self):
        target = self.cleaned_data["status"]
        current = self.instance.status
        if not self.instance.can_transition_to(target):
            labels = dict(InputAllocation.Status.choices)
            raise forms.ValidationError(
                "Cannot change status from {current} to {target}.".format(
                    current=labels.get(current, current),
                    target=labels.get(target, target),
                )
            )
        return target
