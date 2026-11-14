"""Aggregation helpers for the fertilizer distribution audit.

The audit groups allocations by the region and group a member belongs to. A
member can technically sit in more than one structure unit; we use the first
active assignment ordered by unit name so a single allocation is never counted
twice.
"""
from decimal import Decimal

from apps.groups.models import GroupMemberAssignment, StructureUnit

from .models import InputAllocation

ZERO = Decimal("0")
COUNT_FIELDS = ("total", "requested", "verified", "partially_delivered", "delivered", "rejected")
TOTAL_FIELDS = COUNT_FIELDS + ("quantity", "delivered_quantity")


def _region_for(unit, units):
    """Walk up the structure tree and return the first Region ancestor."""
    seen = set()
    while unit is not None and unit.pk not in seen:
        if unit.unit_type == StructureUnit.Type.REGION:
            return unit
        seen.add(unit.pk)
        unit = units.get(unit.parent_id)
    return None


def _blank_row(**extra):
    row = {field: 0 for field in COUNT_FIELDS}
    row.update({"quantity": ZERO, "delivered_quantity": ZERO})
    row.update(extra)
    return row


def build_distribution_audit(organisation, allocations=None):
    """Return per-group and per-region allocation vs delivery totals.

    ``allocations`` can be supplied to reuse an already filtered queryset (for
    example a role-scoped list); otherwise every allocation in the organisation
    is included.
    """
    if allocations is None:
        allocations = InputAllocation.objects.for_organisation(organisation)

    units = {
        unit.pk: unit
        for unit in StructureUnit.objects.for_organisation(organisation).only(
            "pk", "name", "unit_type", "parent_id"
        )
    }
    member_groups = {}
    assignments = (
        GroupMemberAssignment.objects.for_organisation(organisation)
        .select_related("unit")
        .order_by("unit__name")
    )
    for assignment in assignments:
        member_groups.setdefault(assignment.member_id, assignment.unit)

    group_rows = {}
    for allocation in allocations:
        unit = member_groups.get(allocation.member_id)
        region = _region_for(unit, units) if unit else None
        region_name = region.name if region else "Unassigned"
        group_name = unit.name if unit else "No group"
        key = (region_name, group_name)
        row = group_rows.get(key)
        if row is None:
            row = _blank_row(region=region_name, group=group_name)
            group_rows[key] = row
        row["total"] += 1
        row[allocation.status] = row.get(allocation.status, 0) + 1
        row["quantity"] += allocation.quantity
        if allocation.status == InputAllocation.Status.DELIVERED:
            row["delivered_quantity"] += allocation.quantity

    rows = sorted(group_rows.values(), key=lambda row: (row["region"], row["group"]))
    region_rows = {}
    for row in rows:
        region = region_rows.get(row["region"])
        if region is None:
            region = _blank_row(region=row["region"])
            region_rows[row["region"]] = region
        for field in TOTAL_FIELDS:
            region[field] += row[field]

    totals = _blank_row()
    for row in rows:
        for field in TOTAL_FIELDS:
            totals[field] += row[field]

    return {
        "rows": rows,
        "region_rows": sorted(region_rows.values(), key=lambda row: row["region"]),
        "totals": totals,
        "has_data": bool(rows),
    }
