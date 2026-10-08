from django import forms

from apps.members.models import Member
from apps.organisations.models import OrganisationMembership

from .models import GroupMemberAssignment, StructureUnit


class StructureUnitForm(forms.ModelForm):
    class Meta:
        model = StructureUnit
        fields = ["name", "unit_type", "parent", "leader", "field_officer", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, organisation, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)
        self.instance.organisation = organisation
        units = StructureUnit.objects.for_organisation(organisation)
        if self.instance.pk:
            units = units.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = units
        self.fields["leader"].queryset = Member.objects.for_organisation(organisation).filter(status=Member.Status.ACTIVE)
        self.fields["field_officer"].queryset = OrganisationMembership.objects.filter(
            organisation=organisation,
            role=OrganisationMembership.Role.FIELD_OFFICER,
            is_active=True,
            user__is_active=True,
        ).select_related("user")
        self.fields["parent"].required = False
        self.fields["leader"].required = False
        self.fields["field_officer"].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.organisation = self.organisation
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class GroupMemberAssignmentForm(forms.ModelForm):
    class Meta:
        model = GroupMemberAssignment
        fields = ["member", "joined_at"]
        widgets = {"joined_at": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, organisation, unit, **kwargs):
        self.organisation = organisation
        self.unit = unit
        super().__init__(*args, **kwargs)
        self.instance.organisation = organisation
        self.instance.unit = unit
        assigned = unit.member_assignments.values_list("member_id", flat=True)
        self.fields["member"].queryset = Member.objects.for_organisation(organisation).exclude(pk__in=assigned)

    def save(self, commit=True):
        assignment = super().save(commit=False)
        assignment.organisation = self.organisation
        assignment.unit = self.unit
        assignment.full_clean()
        if commit:
            assignment.save()
        return assignment


class NewMemberAssignmentForm(forms.Form):
    """Group-side fields when a brand-new member is created from a group (Kennedy feedback item 6)."""

    joined_at = forms.DateField(
        required=False,
        label="Joined group on",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prefix", "group")
        super().__init__(*args, **kwargs)
