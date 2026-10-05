from django.db.models import Q
from django.shortcuts import get_object_or_404,redirect,render
from django.contrib import messages
from apps.organisations.decorators import manager_or_admin_required,organisation_required
from apps.organisations.scope import operational_staff_required
from .forms import FinancialRecordForm
from .models import FinancialRecord

@operational_staff_required
def finance_list(request):
    records=FinancialRecord.objects.for_organisation(request.organisation).select_related("member","recorded_by")
    q=request.GET.get("q","").strip(); kind=request.GET.get("type",""); status=request.GET.get("status","")
    if q: records=records.filter(Q(member__first_name__icontains=q)|Q(member__last_name__icontains=q)|Q(reference_number__icontains=q)|Q(notes__icontains=q))
    if kind in FinancialRecord.Type.values: records=records.filter(record_type=kind)
    if status in FinancialRecord.Status.values: records=records.filter(status=status)
    return render(request,"finance/list.html",{"records":records,"query":q,"types":FinancialRecord.Type.choices,"statuses":FinancialRecord.Status.choices,"selected_type":kind,"selected_status":status})
@operational_staff_required
def finance_detail(request,record_id):
    item=get_object_or_404(FinancialRecord.objects.for_organisation(request.organisation).select_related("member","recorded_by"),pk=record_id)
    return render(request,"finance/detail.html",{"record":item})
@manager_or_admin_required
def finance_create(request):
    form=FinancialRecordForm(request.POST or None,organisation=request.organisation,recorded_by=request.user)
    if request.method=="POST" and form.is_valid():
        item=form.save(); messages.success(request,"Financial record saved."); return redirect("finance_detail",record_id=item.pk)
    return render(request,"finance/form.html",{"form":form,"title":"Record payment, due or expense"})
@manager_or_admin_required
def finance_edit(request,record_id):
    item=get_object_or_404(FinancialRecord.objects.for_organisation(request.organisation),pk=record_id)
    form=FinancialRecordForm(request.POST or None,instance=item,organisation=request.organisation,recorded_by=request.user)
    if request.method=="POST" and form.is_valid():
        item=form.save(); messages.success(request,"Financial record updated."); return redirect("finance_detail",record_id=item.pk)
    return render(request,"finance/form.html",{"form":form,"title":"Edit financial record","record":item})