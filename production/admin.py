from django.contrib import admin
from .models import *

admin.site.site_header = "Restaurant Admin"
admin.site.site_title = "Restaurant Admin Portal"
admin.site.index_title = "Welcome to Restaurant Admin Portal"   

admin.site.register(Dish)
admin.register(Production)
admin.register(ProductionItem)
admin.register(ProductionIngredients)
admin.register(TimestampModel)
admin.site.register(Ingredient)
admin.site.register(ProductionInventory)
admin.site.register(ProductionRawMaterialAllocation)