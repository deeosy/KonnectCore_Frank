import uuid
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.members.models import Member
from apps.organisations.models import OrganisationMembership,OrganisationOwnedModel

def visit_photo_path(instance,filename): return f"organisations/{instance.organisation_id}/field-visits/{instance.pk}/photo{Path(filename).suffix.lower()}"
class FieldVisit(OrganisationOwnedModel):
 id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
 member=models.ForeignKey(Member,on_delete=models.PROTECT,related_name="field_visits")
 visit_date=models.DateField()
 notes=models.TextField()
 latitude=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
 longitude=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
 photo=models.ImageField(upload_to=visit_photo_path,blank=True)
 recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="field_visits_recorded")
 created_at=models.DateTimeField(auto_now_add=True)
 # One-time form submission key (see apps/core/submissions.py); prevents duplicate records.
 submission_key=models.UUIDField(null=True,blank=True,editable=False)
 submission_fingerprint=models.CharField(max_length=64,blank=True,editable=False)
 class Meta:
  ordering=["-visit_date","-created_at"]
  indexes=[models.Index(fields=["organisation","member"]),models.Index(fields=["organisation","visit_date"])]
  constraints=[models.UniqueConstraint(fields=["organisation","submission_key"],condition=models.Q(submission_key__isnull=False),name="unique_fieldvisit_submission_key")]
 def clean(self):
  e={}
  if self.member_id and self.member.organisation_id!=self.organisation_id:e["member"]="Member must belong to the same organisation."
  if (self.latitude is None)!=(self.longitude is None):e["latitude"]="Enter both GPS coordinates."
  if self.latitude is not None and not Decimal('-90')<=self.latitude<=Decimal('90'):e["latitude"]="Latitude must be between -90 and 90."
  if self.longitude is not None and not Decimal('-180')<=self.longitude<=Decimal('180'):e["longitude"]="Longitude must be between -180 and 180."
  if self.recorded_by_id and not OrganisationMembership.objects.filter(organisation_id=self.organisation_id,user_id=self.recorded_by_id).exists():e["recorded_by"]="Recorder must belong to the same organisation."
  if e:raise ValidationError(e)