from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(User)  # Register your models here, e.g., admin.site.register(User)
admin.site.register(Order)  # Register the Order model
admin.site.register(OrderBudget)  # Register the OrderBuget model