from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404,redirect,render
from apps.collections.forms import CollectionRecordForm
from apps.farms.forms import FarmForm
from apps.farms.models import Farm
from apps.groups.models import GroupMemberAssignment
from apps.members.forms import MemberForm
from apps.members.models import Member,MemberHistory
from apps.members.services import member_snapshot,record_history
from apps.members.views import save_member_form
from apps.organisations.decorators import organisation_required
from apps.organisations.models import OrganisationMembership
from .forms import FieldVisitForm

def assigned_members(request):
 m=request.organisation_membership
 if m.role in (OrganisationMembership.Role.ADMIN,OrganisationMembership.Role.MANAGER):return Member.objects.for_organisation(request.organisation)
 return Member.objects.for_organisation(request.organisation).filter(group_assignments__unit__field_officer=m,group_assignments__unit__is_active=True).distinct()
def field_only(view):
 @organisation_required
 def wrapped(request,*a,**k):
  if request.organisation_membership.role!=OrganisationMembership.Role.FIELD_OFFICER:raise PermissionDenied
  return view(request,*a,**k)
 return wrapped
@organisation_required
def home(request):
 qs=assigned_members(request);q=request.GET.get('q','').strip()
 if q:qs=qs.filter(Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(membership_number__icontains=q)|Q(phone__icontains=q))
 return render(request,'field/home.html',{'members':qs,'query':q})
@field_only
def register_member(request):
 form=MemberForm(request.POST or None,request.FILES or None,organisation=request.organisation)
 if request.method=='POST' and form.is_valid():
  x=save_member_form(form,organisation=request.organisation,actor=request.user,creating=True)
  if x is not None:
   record_history(x,MemberHistory.Action.CREATED,request.user,{"member":member_snapshot(x)});messages.success(request,'Member registered. Ask a Manager to assign the member to your group.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':'Register member'})
@field_only
def visit_add(request,member_id):
 member=get_object_or_404(assigned_members(request),pk=member_id);form=FieldVisitForm(request.POST or None,request.FILES or None,organisation=request.organisation,member=member,recorded_by=request.user)
 if request.method=='POST' and form.is_valid():form.save();messages.success(request,'Field visit saved.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':f'Visit: {member.full_name}'})
@field_only
def farm_update(request,member_id):
 member=get_object_or_404(assigned_members(request),pk=member_id);farm=Farm.objects.for_organisation(request.organisation).filter(member=member).first();form=FarmForm(request.POST or None,instance=farm,organisation=request.organisation,initial={'member':member});form.fields['member'].disabled=True
 if request.method=='POST' and form.is_valid():form.save();messages.success(request,'Farm information saved.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':f'Farm: {member.full_name}'})
@field_only
def collection_add(request,member_id):
 member=get_object_or_404(assigned_members(request),pk=member_id);form=CollectionRecordForm(request.POST or None,request.FILES or None,organisation=request.organisation,recorded_by=request.user,initial={'member':member});form.fields['member'].disabled=True
 if request.method=='POST' and form.is_valid():form.save();messages.success(request,'Collection recorded.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':f'Collection: {member.full_name}'})