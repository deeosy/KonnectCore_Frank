from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404,redirect,render
import mimetypes
from django.http import FileResponse,Http404
from .models import FieldVisit
from apps.collections.forms import CollectionRecordForm
from apps.farms.forms import FarmForm,MemberFarmForm
from apps.farms.models import Farm
from apps.groups.models import GroupMemberAssignment
from apps.members.forms import MemberForm
from apps.members.models import Member,MemberHistory
from apps.members.services import member_snapshot,record_history
from apps.members.views import create_member_with_farm,save_member_form
from apps.organisations.decorators import organisation_required
from apps.organisations.models import OrganisationMembership
from apps.organisations.scope import visible_members
from apps.core.submissions import SubmissionConflict,save_once
from .forms import FieldVisitForm

def assigned_members(request):
 """Field Workspace member scope; delegates to the single owner in organisations.scope."""
 return visible_members(request)
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
 recent_visits=FieldVisit.objects.none()
 if request.organisation_membership.role==OrganisationMembership.Role.FIELD_OFFICER:
  # Only visits this officer recorded, for members still within their scope.
  recent_visits=FieldVisit.objects.for_organisation(request.organisation).filter(recorded_by=request.user,member_id__in=visible_members(request).values('pk')).select_related('member')[:5]
 return render(request,'field/home.html',{'members':qs,'query':q,'recent_visits':recent_visits})
@field_only
def register_member(request):
 form=MemberForm(request.POST or None,request.FILES or None,organisation=request.organisation)
 farm_form=MemberFarmForm(request.POST or None,organisation=request.organisation)
 if request.method=='POST':
  member_valid=form.is_valid();farm_valid=farm_form.is_valid()
  if member_valid and farm_valid:
   x=create_member_with_farm(form,farm_form,organisation=request.organisation,actor=request.user)
   if x is not None:
    messages.success(request,f'{x.full_name} has been added and is awaiting assignment. The member will appear in your list once an Admin or Manager adds them to one of your groups.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'farm_form':farm_form,'title':'Add member'})
@field_only
def member_detail(request,member_id):
 """Read-only member page limited to the officer's assigned members (404 otherwise)."""
 member=get_object_or_404(visible_members(request).prefetch_related("farms__crop_seasons__crop","collection_records__crop","collection_records__recorded_by","field_visits__recorded_by"),pk=member_id)
 return render(request,'field/member_detail.html',{'member':member})
@field_only
def visit_add(request,member_id):
 member=get_object_or_404(assigned_members(request),pk=member_id);form=FieldVisitForm(request.POST or None,request.FILES or None,organisation=request.organisation,member=member,recorded_by=request.user)
 if request.method=='POST' and form.is_valid():
  try:
   visit,created=save_once(form,organisation=request.organisation,actor=request.user)
  except SubmissionConflict as exc:
   form.add_error(None,str(exc))
  else:
   messages.success(request,'Field visit saved.' if created else 'This field visit was already saved.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':f'Visit: {member.full_name}'})
@field_only
def farm_update(request,member_id):
 member=get_object_or_404(assigned_members(request),pk=member_id);farm=Farm.objects.for_organisation(request.organisation).filter(member=member).first();form=FarmForm(request.POST or None,instance=farm,organisation=request.organisation,initial={'member':member});form.fields['member'].disabled=True
 if request.method=='POST' and form.is_valid():form.save();messages.success(request,'Farm information saved.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':f'Farm: {member.full_name}'})
@field_only
def collection_add(request,member_id):
 member=get_object_or_404(assigned_members(request),pk=member_id);form=CollectionRecordForm(request.POST or None,request.FILES or None,organisation=request.organisation,recorded_by=request.user,initial={'member':member});form.fields['member'].disabled=True
 if request.method=='POST' and form.is_valid():
  try:
   record,created=save_once(form,organisation=request.organisation,actor=request.user)
  except SubmissionConflict as exc:
   form.add_error(None,str(exc))
  else:
   messages.success(request,'Collection recorded.' if created else 'This collection was already saved.');return redirect('field_home')
 return render(request,'field/form.html',{'form':form,'title':f'Collection: {member.full_name}'})
@organisation_required
def visit_photo(request,visit_id):
 """Serve a field visit photo only for members the user may see (404 otherwise, including other organisations)."""
 visit=get_object_or_404(FieldVisit.objects.for_organisation(request.organisation).filter(member_id__in=visible_members(request).values('pk')),pk=visit_id)
 if not visit.photo:raise Http404('Visit has no photo.')
 content_type=mimetypes.guess_type(visit.photo.name)[0] or 'application/octet-stream'
 return FileResponse(visit.photo.open('rb'),content_type=content_type)