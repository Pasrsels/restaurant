from django.contrib import admin
from .models import *


for model in [
    Meal, 
    Supplier, 
    Production, 
    Ingredient, 
    PurchaseOrder, 
    MealCategory, 
    UnitOfMeasurement, 
    ProductionItems, 
    TransferItems,
    BudgetItem, 
    StockTake, 
    StockTakeItem,
    EndOfDay,
    EndOfDayItems,
    EndOfDayCashier
]:
    admin.site.register(model)