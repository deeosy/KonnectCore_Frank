from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.collections.models import CollectionRecord
from apps.farms.models import Crop, Farm, FarmCropSeason
from apps.field.models import FieldVisit
from apps.finance.models import FinancialRecord, PaymentAllocation
from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member, MemberHistory
from apps.organisations.models import Organisation, OrganisationMembership


MEMBERS = [
    ("KC-001", "Ama", "Mensah", "024 321 9001", "Ejura", "active"),
    ("KC-002", "Kwame", "Owusu", "020 482 1134", "Ejura", "active"),
    ("KC-003", "Akosua", "Boateng", "055 714 2290", "Kasei", "active"),
    ("KC-004", "Kojo", "Asare", "024 813 4402", "Kasei", "active"),
    ("KC-005", "Abena", "Osei", "050 361 7855", "Anyinasu", "active"),
    ("KC-006", "Yaw", "Darko", "027 540 1903", "Anyinasu", "active"),
    ("KC-007", "Adwoa", "Nyarko", "024 992 0516", "Mampong", "active"),
    ("KC-008", "Kofi", "Antwi", "054 170 3382", "Mampong", "active"),
    ("KC-009", "Afia", "Badu", "020 849 6207", "Ejura", "active"),
    ("KC-010", "Nana", "Agyeman", "024 675 4120", "Kasei", "active"),
    ("KC-011", "Esi", "Appiah", "059 311 8706", "Anyinasu", "active"),
    ("KC-012", "Yaa", "Frimpong", "027 914 2058", "Mampong", "active"),
    ("KC-013", "Kwaku", "Opoku", "050 608 3319", "Ejura", "active"),
    ("KC-014", "Mavis", "Addo", "024 247 9063", "Kasei", "inactive"),
    ("KC-015", "Samuel", "Tetteh", "055 832 1470", "Anyinasu", "active"),
    ("KC-016", "Grace", "Amankwah", "020 190 5764", "Mampong", "active"),
    ("KC-017", "Daniel", "Acheampong", "054 751 3098", "Ejura", "suspended"),
    ("KC-018", "Comfort", "Sarpong", "027 468 2251", "Kasei", "active"),
    ("KC-019", "Joseph", "Bonsu", "024 536 8804", "Anyinasu", "active"),
    ("KC-020", "Linda", "Koomson", "050 917 6432", "Mampong", "active"),
    ("KC-021", "Emmanuel", "Baah", "020 344 1059", "Ejura", "active"),
    ("KC-022", "Patience", "Amoako", "055 629 7718", "Kasei", "active"),
    ("KC-023", "Isaac", "Gyasi", "024 108 4927", "Anyinasu", "inactive"),
    ("KC-024", "Rose", "Arthur", "027 783 0165", "Mampong", "active"),
]


class Command(BaseCommand):
    help = "Seed realistic, idempotent validation data into one existing organisation."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="Target organisation slug")
        parser.add_argument("--staff-password", help="Password used only for newly created demo staff")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            org = Organisation.objects.get(slug=options["organisation"])
        except Organisation.DoesNotExist as exc:
            raise CommandError("Organisation does not exist.") from exc
        if org.status != Organisation.Status.ACTIVE:
            raise CommandError("Demo data can only be added to an active organisation.")

        admin_membership = org.memberships.filter(role=OrganisationMembership.Role.ADMIN, is_active=True).select_related("user").first()
        if not admin_membership:
            raise CommandError("The organisation needs an active Admin first.")
        admin = admin_membership.user
        password = options.get("staff_password")

        manager = self._staff(org, "manager@demo.konnectcore.local", "Esi", "Manager", OrganisationMembership.Role.MANAGER, password)
        officer_north = self._staff(org, "field.north@demo.konnectcore.local", "Kojo", "Adu", OrganisationMembership.Role.FIELD_OFFICER, password)
        officer_south = self._staff(org, "field.south@demo.konnectcore.local", "Akua", "Yeboah", OrganisationMembership.Role.FIELD_OFFICER, password)

        today = timezone.localdate()
        members = {}
        for i, (number, first, last, phone, location, status) in enumerate(MEMBERS):
            member, created = Member.objects.get_or_create(
                organisation=org,
                membership_number=number,
                defaults={
                    "first_name": first, "last_name": last, "phone": phone,
                    "id_reference": f"GHA-{820000000 + i}", "location": location,
                    "status": status, "created_by": admin, "updated_by": admin,
                },
            )
            members[number] = member
            if created:
                MemberHistory.objects.create(
                    organisation=org, member=member, action=MemberHistory.Action.CREATED,
                    changes={}, actor=admin,
                )

        region = self._unit(org, "Ashanti Region", StructureUnit.Type.REGION)
        district = self._unit(org, "Ejura Sekyedumase District", StructureUnit.Type.DISTRICT, region)
        groups = [
            self._unit(org, "Ejura Maize Growers", StructureUnit.Type.GROUP, district, officer_north, members["KC-001"]),
            self._unit(org, "Kasei Women Farmers", StructureUnit.Type.GROUP, district, officer_north, members["KC-003"]),
            self._unit(org, "Anyinasu Producers", StructureUnit.Type.GROUP, district, officer_south, members["KC-005"]),
            self._unit(org, "Mampong Harvest Circle", StructureUnit.Type.GROUP, district, officer_south, members["KC-007"]),
        ]
        for i, member in enumerate(members.values()):
            GroupMemberAssignment.objects.get_or_create(
                organisation=org, unit=groups[i % 4], member=member,
                defaults={"joined_at": today - timedelta(days=560 - i * 11)},
            )

        crops = {}
        for name, variety in [("Maize", "Obatanpa"), ("Cocoa", "Hybrid"), ("Cassava", "Bankye Hemaa"), ("Soybean", "Jenguma")]:
            crop, _ = Crop.objects.get_or_create(organisation=org, name=name, variety=variety)
            crops[name] = crop

        farms = []
        for i, member in enumerate(members.values()):
            farm, _ = Farm.objects.get_or_create(
                organisation=org, member=member, name="Main farm",
                defaults={
                    "size": Decimal(str(1.6 + (i % 7) * 0.55)),
                    "size_unit": Farm.SizeUnit.HECTARES,
                    "location": f"{member.location} farming zone",
                    "latitude": Decimal("7.385000") + Decimal(i) / Decimal("1000"),
                    "longitude": Decimal("-1.356000") - Decimal(i) / Decimal("1000"),
                    "notes": "Primary production plot monitored by the cooperative.",
                },
            )
            farms.append(farm)
            crop = list(crops.values())[i % len(crops)]
            FarmCropSeason.objects.get_or_create(
                organisation=org, farm=farm, crop=crop, season="2026 Major Season",
                defaults={
                    "planting_start": today - timedelta(days=145 - i % 20),
                    "planting_end": today - timedelta(days=132 - i % 20),
                    "estimated_yield": Decimal(2100 + i * 85),
                    "actual_yield": Decimal(1780 + i * 72) if i < 16 else None,
                    "yield_unit": FarmCropSeason.YieldUnit.KILOGRAMS,
                    "notes": "Season profile created for validation and planning.",
                },
            )

        active_members = [m for m in members.values() if m.status == Member.Status.ACTIVE]
        collections = []
        for i in range(34):
            member = active_members[i % len(active_members)]
            crop = list(crops.values())[i % len(crops)]
            date = today - timedelta(days=i * 3 + 1)
            quantity = Decimal(320 + (i % 8) * 65)
            price = {"Maize": Decimal("4.20"), "Cocoa": Decimal("18.50"), "Cassava": Decimal("2.75"), "Soybean": Decimal("7.80")}[crop.name]
            collection, _ = CollectionRecord.objects.get_or_create(
                organisation=org, notes=f"Demo collection record {i + 1:03d}.",
                defaults={
                    "member": member, "crop": crop, "collection_date": date,
                    "collection_location": f"{member.location} collection point",
                    "quantity": quantity, "quantity_unit": CollectionRecord.QuantityUnit.KILOGRAMS,
                    "quality_grade": ["Grade A", "Grade B", "Premium"][i % 3],
                    "price_per_unit": price,
                    "recorded_by": officer_north.user if i % 2 == 0 else officer_south.user,
                },
            )
            collections.append(collection)

        statuses = [FinancialRecord.Status.PAID, FinancialRecord.Status.PAID, FinancialRecord.Status.PART_PAID, FinancialRecord.Status.PENDING]
        methods = [FinancialRecord.Method.MOBILE_MONEY, FinancialRecord.Method.CASH, FinancialRecord.Method.BANK_TRANSFER]
        for i in range(28):
            member = active_members[i % len(active_members)]
            record_type = [FinancialRecord.Type.MEMBER_PAYMENT, FinancialRecord.Type.DUE, FinancialRecord.Type.CONTRIBUTION, FinancialRecord.Type.SAVING][i % 4]
            status = statuses[i % len(statuses)]
            amount = Decimal(180 + (i % 6) * 75)
            paid = amount if status == FinancialRecord.Status.PAID else (amount / 2 if status == FinancialRecord.Status.PART_PAID else Decimal("0"))
            ref = f"DEMO-FIN-{i + 1:03d}"
            record, _ = FinancialRecord.objects.get_or_create(
                organisation=org, reference_number=ref,
                defaults={
                    "record_type": record_type, "member": member, "amount": amount,
                    "paid_amount": paid, "payment_method": methods[i % len(methods)],
                    "status": status, "payment_date": today - timedelta(days=i * 4 + 2),
                    "notes": "Validation dataset transaction.", "recorded_by": manager.user,
                    "purpose": FinancialRecord.Purpose.COLLECTIONS if record_type == FinancialRecord.Type.MEMBER_PAYMENT else "",
                },
            )
            # Demo payments to members settle a collection of the same member, so they show as allocated.
            if (record.record_type == FinancialRecord.Type.MEMBER_PAYMENT and record.purpose == FinancialRecord.Purpose.COLLECTIONS
                    and record.paid_amount > 0 and not record.allocations.filter(removed_at__isnull=True).exists()):
                allocation = PaymentAllocation(organisation=org, payment=record, collection=collections[i], amount=record.paid_amount, created_by=manager.user)
                allocation.full_clean()
                allocation.save()
        for i, (note, amount) in enumerate([("Transport for field monitoring", 680), ("Collection centre supplies", 1240), ("Farmer training materials", 950)]):
            FinancialRecord.objects.get_or_create(
                organisation=org, reference_number=f"DEMO-EXP-{i + 1:03d}",
                defaults={
                    "record_type": FinancialRecord.Type.EXPENSE, "member": None,
                    "amount": Decimal(amount), "paid_amount": Decimal(amount),
                    "payment_method": FinancialRecord.Method.BANK_TRANSFER,
                    "status": FinancialRecord.Status.PAID,
                    "payment_date": today - timedelta(days=12 + i * 15),
                    "notes": note, "recorded_by": manager.user,
                },
            )

        for i in range(12):
            member = active_members[i]
            date = today - timedelta(days=i * 5 + 1)
            FieldVisit.objects.get_or_create(
                organisation=org, notes=f"Demo field visit {i + 1:03d}: " + [
                    "Crop condition is healthy; advised timely weeding.",
                    "Reviewed farm records and confirmed planting progress.",
                    "Discussed pest control and next collection date.",
                ][i % 3],
                defaults={
                    "member": member, "visit_date": date,
                    "latitude": Decimal("7.385000") + Decimal(i) / Decimal("1000"),
                    "longitude": Decimal("-1.356000") - Decimal(i) / Decimal("1000"),
                    "recorded_by": officer_north.user if i % 2 == 0 else officer_south.user,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Demo ready for {org.name}: {Member.objects.for_organisation(org).count()} members, "
            f"{StructureUnit.objects.for_organisation(org).filter(unit_type=StructureUnit.Type.GROUP).count()} groups, "
            f"{Farm.objects.for_organisation(org).count()} farms, "
            f"{CollectionRecord.objects.for_organisation(org).count()} collections, "
            f"{FinancialRecord.objects.for_organisation(org).count()} financial records, "
            f"{FieldVisit.objects.for_organisation(org).count()} visits."
        ))

    def _staff(self, org, email, first, last, role, password):
        user, created = get_user_model().objects.get_or_create(email=email, defaults={"first_name": first, "last_name": last})
        if created:
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()
        membership, _ = OrganisationMembership.objects.update_or_create(
            organisation=org, user=user, defaults={"role": role, "is_active": True}
        )
        return membership

    def _unit(self, org, name, unit_type, parent=None, officer=None, leader=None):
        unit, _ = StructureUnit.objects.get_or_create(
            organisation=org, parent=parent, name=name,
            defaults={"unit_type": unit_type, "description": "Demo organisation structure", "is_active": True},
        )
        changed = False
        for field, value in (("field_officer", officer), ("leader", leader)):
            if value and getattr(unit, f"{field}_id") != value.pk:
                setattr(unit, field, value); changed = True
        if changed:
            unit.full_clean(); unit.save()
        return unit
