from django.contrib import messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .decorators import admin_required, organisation_required
from .forms import AcceptInvitationForm, LoginForm, PlatformOrganisationForm, PlatformOrganisationStatusForm, StaffCreateForm, StaffInviteForm
from .invitations import StaffInvitation
from django.views.decorators.http import require_POST
from .middleware import ActiveOrganisationMiddleware
from .models import Organisation, OrganisationMembership


def membership_home(membership):
    if membership.role == OrganisationMembership.Role.FIELD_OFFICER:
        return "field_home"
    return "workspace"


class RoleAwareLoginView(auth_views.LoginView):
    authentication_form = LoginForm

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        if self.request.user.is_superuser:
            return redirect("platform_organisations").url
        memberships = OrganisationMembership.objects.select_related("organisation").filter(
            user=self.request.user,
            is_active=True,
            organisation__status=Organisation.Status.ACTIVE,
        )
        if memberships.count() == 1:
            membership = memberships.first()
            self.request.session[ActiveOrganisationMiddleware.SESSION_KEY] = membership.organisation_id
            return redirect(membership_home(membership)).url
        return redirect("choose_organisation").url

@login_required
def entrypoint(request):
    if request.user.is_superuser: return redirect("platform_organisations")
    if request.organisation: return redirect(membership_home(request.organisation_membership))
    return redirect("choose_organisation")

@login_required
def choose_organisation(request):
    if request.user.is_superuser: return redirect("platform_organisations")
    memberships = OrganisationMembership.objects.select_related("organisation").filter(user=request.user, is_active=True, organisation__status=Organisation.Status.ACTIVE)
    if request.method == "POST":
        membership = get_object_or_404(memberships, organisation_id=request.POST.get("organisation"))
        request.session[ActiveOrganisationMiddleware.SESSION_KEY] = membership.organisation_id
        return redirect(membership_home(membership))
    return render(request, "organisations/choose.html", {"memberships": memberships})

@organisation_required
def workspace(request):
    from apps.reports.views import dashboard
    return dashboard(request)

@admin_required
def staff_list(request):
    staff = OrganisationMembership.objects.select_related("user").filter(organisation=request.organisation)
    invitations = StaffInvitation.objects.filter(organisation=request.organisation, accepted_at__isnull=True, cancelled_at__isnull=True)
    return render(request, "organisations/staff_list.html", {"staff": staff, "invitations": invitations})

@admin_required
def staff_create(request):
    form = StaffCreateForm(request.POST or None, organisation=request.organisation)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Staff user created."); return redirect("staff_list")
    return render(request, "organisations/form.html", {"form": form, "title": "Create staff user"})

@admin_required
def staff_invite(request):
    form = StaffInviteForm(request.POST or None)
    invite_url = None
    if request.method == "POST" and form.is_valid():
        existing = OrganisationMembership.objects.filter(organisation=request.organisation, user__email__iexact=form.cleaned_data["email"]).exists()
        if existing:
            form.add_error("email", "This user already belongs to the organisation.")
        else:
            _, token = StaffInvitation.issue(organisation=request.organisation, email=form.cleaned_data["email"], role=form.cleaned_data["role"], invited_by=request.user)
            invite_url = request.build_absolute_uri(f"/invitations/{token}/accept/")
            messages.success(request, "Invitation created. Share the secure link below; it expires in 7 days.")
    return render(request, "organisations/form.html", {"form": form, "title": "Invite staff user", "invite_url": invite_url})

@admin_required
@require_POST
def staff_invitation_cancel(request, invitation_id):
    # Only pending invitations in the active organisation can be cancelled; the record is kept for audit.
    invitation = get_object_or_404(StaffInvitation, pk=invitation_id, organisation=request.organisation, accepted_at__isnull=True, cancelled_at__isnull=True)
    invitation.cancelled_at = timezone.now()
    invitation.cancelled_by = request.user
    invitation.save(update_fields=["cancelled_at", "cancelled_by"])
    messages.success(request, f"Invitation for {invitation.email} cancelled. The link no longer works.")
    return redirect("staff_list")

def accept_invitation(request, token):
    invitation = get_object_or_404(StaffInvitation.objects.select_related("organisation"), token_hash=StaffInvitation.digest(token))
    if not invitation.is_valid: raise PermissionDenied("Invitation is invalid or expired.")
    form = AcceptInvitationForm(request.POST or None, email=invitation.email)
    if request.method == "POST" and form.is_valid():
        user = form.save(invitation)
        invitation.accepted_at = timezone.now(); invitation.save(update_fields=["accepted_at"])
        login(request, user); request.session[ActiveOrganisationMiddleware.SESSION_KEY] = invitation.organisation_id
        membership = OrganisationMembership.objects.get(user=user, organisation=invitation.organisation)
        return redirect(membership_home(membership))
    return render(request, "organisations/accept_invitation.html", {"form": form, "invitation": invitation})

@user_passes_test(lambda u: u.is_superuser, login_url="login")
def platform_organisations(request):
    organisations = Organisation.objects.annotate(user_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True), member_count=Count("member", distinct=True)).order_by("name")
    return render(request, "platform/organisation_list.html", {"organisations": organisations})

@user_passes_test(lambda u: u.is_superuser, login_url="login")
def platform_organisation_create(request):
    form = PlatformOrganisationForm(request.POST or None)
    invite_url = None
    if request.method == "POST" and form.is_valid():
        _, _, token = form.save(created_by=request.user)
        invite_url = request.build_absolute_uri(f"/invitations/{token}/accept/")
        messages.success(request, "Organisation created. Share the first Admin invitation link below.")
    return render(request, "platform/organisation_form.html", {"form": form, "invite_url": invite_url})

@user_passes_test(lambda u: u.is_superuser, login_url="login")
def platform_organisation_detail(request, organisation_id):
    organisation = get_object_or_404(
        Organisation.objects.annotate(
            user_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True),
            member_count=Count("member", distinct=True),
        ),
        pk=organisation_id,
    )
    memberships = organisation.memberships.select_related("user").order_by("role", "user__email")
    form = PlatformOrganisationStatusForm(request.POST or None, instance=organisation)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Organisation account status updated.")
        return redirect("platform_organisation_detail", organisation_id=organisation.pk)
    return render(request, "platform/organisation_detail.html", {
        "organisation": organisation,
        "memberships": memberships,
        "form": form,
    })