from django.contrib import admin

from .models import Crop, Farm, FarmCropSeason

admin.site.register(Crop)
admin.site.register(Farm)
admin.site.register(FarmCropSeason)