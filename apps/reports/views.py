import csv
from io import BytesIO
from django.db.models import Count,Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from openpyxl import Workbook
from apps.collections.models import CollectionRecord
from apps.finance.models import FinancialRecord
from apps.farms.models import Crop, Farm
from apps.groups.models import GroupMemberAssignment,StructureUnit
from apps.members.models import Member, MemberHistory
from apps.organisations.decorators import manager_or_admin_required,organisation_required

def _filters(request, queryset, kind):
    member=request.GET.get("member","").strip();crop=request.GET.get("crop","").strip();group=request.GET.get("group","").strip();status=request.GET.get("status","").strip();start=request.GET.get("date_from","").strip();end=request.GET.get("date_to","").strip()
    valid_members={str(x) for x in Member.objects.for_organisation(request.organisation).values_list("pk",flat=True)}
    if member in valid_members: queryset=queryset.filter(member_id=member)
    valid_groups={str(x) for x in StructureUnit.objects.for_organisation(request.organisation).values_list("pk",flat=True)}
    if group in valid_groups:
        ids=GroupMemberAssignment.objects.for_organisation(request.organisation).filter(unit_id=group).values("member_id")
        queryset=queryset.filter(member_id__in=ids)
    if kind=="collections":
        valid_crops={str(x) for x in Crop.objects.for_organisation(request.organisation).values_list("pk",flat=True)}
        if crop in valid_crops: queryset=queryset.filter(crop_id=crop)
        if start: queryset=queryset.filter(collection_date__gte=start)
        if end: queryset=queryset.filter(collection_date__lte=end)
    elif kind=="finance":
        if status in FinancialRecord.Status.values: queryset=queryset.filter(status=status)
        if start: queryset=queryset.filter(payment_date__gte=start)
        if end: queryset=queryset.filter(payment_date__lte=end)
    return queryset

@organisation_required
def dashboard(request):
    org = request.organisation
    members = Member.objects.for_organisation(org)
    collections = CollectionRecord.objects.for_organisation(org).select_related("member", "crop", "recorded_by")
    finance = FinancialRecord.objects.for_organisation(org).select_related("member", "recorded_by")
    quantities = list(collections.values("quantity_unit").annotate(total=Sum("quantity")).order_by("quantity_unit"))
    payment_rows = finance.exclude(record_type=FinancialRecord.Type.EXPENSE)
    payments = sum((row.paid_amount for row in payment_rows), 0)
    outstanding_rows = finance.filter(
        record_type__in=[FinancialRecord.Type.MEMBER_PAYMENT, FinancialRecord.Type.DUE]
    ).exclude(status=FinancialRecord.Status.CANCELLED)
    outstanding = sum((row.outstanding_amount for row in outstanding_rows), 0)
    groups = StructureUnit.objects.for_organisation(org).filter(
        unit_type=StructureUnit.Type.GROUP, is_active=True
    )
    metrics = {
        "members": members.count(),
        "active_members": members.filter(status=Member.Status.ACTIVE).count(),
        "groups": groups.count(),
        "farms": Farm.objects.for_organisation(org).count(),
        "collections": collections.count(),
        "quantities": quantities,
        "payments": payments,
        "outstanding": outstanding,
    }
    return render(request, "reports/dashboard.html", {
        "metrics": metrics,
        "recent_collections": collections[:5],
        "recent_payments": finance[:5],
        "group_summary": groups.annotate(total_members=Count("member_assignments")).order_by("-total_members", "name")[:6],
        "crop_totals": collections.values("crop__name", "crop__variety", "quantity_unit").annotate(total=Sum("quantity")).order_by("-total")[:6],
        "recent_activity": MemberHistory.objects.for_organisation(org).select_related("member", "actor")[:6],
    })
@organisation_required
def reports_home(request):
    org=request.organisation
    collections=_filters(request,CollectionRecord.objects.for_organisation(org).select_related("member","crop"),"collections")
    finance=_filters(request,FinancialRecord.objects.for_organisation(org).select_related("member"),"finance")
    members=Member.objects.for_organisation(org)
    groups=StructureUnit.objects.for_organisation(org).annotate(total_members=Count("member_assignments"))
    return render(request,"reports/home.html",{"collections":collections[:100],"finance":finance[:100],"member_rows":members[:100],"group_rows":groups[:100],"members":members,"groups":groups,"crops":Crop.objects.for_organisation(org),"statuses":FinancialRecord.Status.choices,"querystring":request.GET.urlencode()})

def _rows(request,report):
    org=request.organisation
    if report=="members":
        return ["Membership number","First name","Last name","Phone","Location","Status"],([m.membership_number,m.first_name,m.last_name,m.phone,m.location,m.get_status_display()] for m in Member.objects.for_organisation(org))
    if report=="collections":
        qs=_filters(request,CollectionRecord.objects.for_organisation(org).select_related("member","crop"),"collections")
        return ["Date","Member","Membership number","Crop","Quantity","Unit","Grade","Location","Price per unit","Total value"],([x.collection_date,x.member.full_name,x.member.membership_number,x.crop.display_name,x.quantity,x.get_quantity_unit_display(),x.quality_grade,x.collection_location,x.price_per_unit,x.total_value] for x in qs)
    if report=="finance":
        qs=_filters(request,FinancialRecord.objects.for_organisation(org).select_related("member"),"finance")
        return ["Date","Type","Member","Amount","Paid","Outstanding","Method","Status","Reference"],([x.payment_date,x.get_record_type_display(),x.member.full_name if x.member else "Organisation",x.amount,x.paid_amount,x.outstanding_amount,x.get_payment_method_display(),x.get_status_display(),x.reference_number] for x in qs)
    if report=="groups":
        qs=StructureUnit.objects.for_organisation(org).select_related("parent","leader","field_officer__user").annotate(total_members=Count("member_assignments"))
        return ["Name","Type","Parent","Leader","Field Officer","Members","Active"],([x.name,x.get_unit_type_display(),x.parent.name if x.parent else "",x.leader.full_name if x.leader else "",str(x.field_officer.user) if x.field_officer else "",x.total_members,"Yes" if x.is_active else "No"] for x in qs)
    raise ValueError("Unknown report")

@manager_or_admin_required
def export_report(request,report,format):
    if report not in {"members","collections","finance","groups"} or format not in {"csv","xlsx"}: return HttpResponse(status=404)
    headers,rows=_rows(request,report);filename=f"{report}-report.{format}"
    if format=="csv":
        response=HttpResponse(content_type="text/csv");response["Content-Disposition"]=f'attachment; filename="{filename}"';writer=csv.writer(response);writer.writerow(headers);writer.writerows(rows);return response
    wb=Workbook();ws=wb.active;ws.title=report.title();ws.append(headers)
    for row in rows:ws.append(list(row))
    stream=BytesIO();wb.save(stream);response=HttpResponse(stream.getvalue(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");response["Content-Disposition"]=f'attachment; filename="{filename}"';return response