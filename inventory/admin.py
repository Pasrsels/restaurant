from django.contrib import admin
from .models import *


for model in [
    Supplier, 
    PurchaseOrder, 
    UnitOfMeasurement, 
    TransferItems,
    BudgetItem, 
    StockTake, 
    StockTakeItem,
    EndOfDay,
    EndOfDayItems,
    EndOfDayCashier,
    Logs,
]:
    admin.site.register(model)