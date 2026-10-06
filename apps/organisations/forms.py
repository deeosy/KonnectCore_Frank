from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction
from django.utils.text import slugify
from .models import Organisation, OrganisationMembership
from .invitations import StaffInvitation

User = get_user_model()
class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

class PlatformOrganisationForm(forms.ModelForm):
    admin_email = forms.EmailField()
    admin_first_name = forms.CharField(max_length=150)
    admin_last_name = forms.CharField(max_length=150, required=False)
    class Meta:
        model = Organisation
        fields = ["name", "slug", "currency", "status"]
    def clean_currency(self):
        return (self.cleaned_data.get("currency") or "").strip().upper()
    def clean_admin_email(self):
        value = self.cleaned_data["admin_email"].strip().lower()
        if User.objects.filter(email=value).exists(): raise forms.ValidationError("A user with this email already exists.")
        return value
    @transaction.atomic
    def save(self, *, created_by):
        organisation = super().save()
        invitation, token = StaffInvitation.issue(organisation=organisation, email=self.cleaned_data["admin_email"], role=OrganisationMembership.Role.ADMIN, invited_by=created_by)
        return organisation, invitation, token

class PlatformOrganisationStatusForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = ["status"]

class StaffCreateForm(UserCreationForm):
    role = forms.ChoiceField(choices=OrganisationMembership.Role.choices)
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["email", "first_name", "last_name"]
    def __init__(self, *args, organisation, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists(): raise forms.ValidationError("A user with this email already exists.")
        return email
    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=commit)
        OrganisationMembership.objects.create(organisation=self.organisation, user=user, role=self.cleaned_data["role"])
        return user

class StaffInviteForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=OrganisationMembership.Role.choices)
    def clean_email(self): return self.cleaned_data["email"].strip().lower()

class AcceptInvitationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "last_name"]
    def __init__(self, *args, email, **kwargs):
        self.invited_email = email
        super().__init__(*args, **kwargs)
    @transaction.atomic
    def save(self, invitation):
        user = User.objects.filter(email=self.invited_email).first()
        if user:
            user.set_password(self.cleaned_data["password1"])
            user.first_name = self.cleaned_data["first_name"]
            user.last_name = self.cleaned_data["last_name"]
            user.save()
        else:
            user = User.objects.create_user(email=self.invited_email, password=self.cleaned_data["password1"], first_name=self.cleaned_data["first_name"], last_name=self.cleaned_data["last_name"])
        OrganisationMembership.objects.update_or_create(organisation=invitation.organisation, user=user, defaults={"role": invitation.role, "is_active": True})
        return user
