from datetime import datetime
from django import template
from decimal import Decimal
from finance.models import Sale
from production.models import ProductionItem, ProductionIngredients, Production


register = template.Library()

@register.filter
def get_ingredient_item(dictionary, key):
    return dictionary.get(key, [])

@register.filter
def calculate_dish_total_cost(item, portions):
    return item.dish.cost * Decimal(portions) if portions else 0

@register.filter
def calculate_total_ing_cost(production_ingredients):
    if production_ingredients:
        return round(sum(item.ingredient.cost * Decimal(item.actual_quantity) if item.actual_quantity else 0  for item in production_ingredients), 2)
    return 0

@register.filter
def calculate_total_cost(production):
    if production:
        production_items = ProductionItem.objects.filter(production=production).select_related('dish')
        return round(sum(item.dish.cost * Decimal(item.declared_portions) if item.declared_portions else 0 for item in production_items), 2)
    return 0

@register.filter
def calculate_ingredient_cost(ing, kgs):
    if kgs:
        return ing.ingredient.cost * Decimal(kgs)
    return 0

@register.filter
def calculate_total_dish_cost(production_plan_items):
    if production_plan_items:
        return round(sum(item.dish.cost * Decimal(item.declared_portions) if item.declared_portions else 0 for item in production_plan_items), 2)
    return 0

@register.filter
def calculate_total_dish_revenue(production_plan_items):
    if production_plan_items:
        return round(sum(item.dish.price * Decimal(item.declared_portions) if item.declared_portions else 0 for item in production_plan_items), 2)
    return 0

@register.filter
def calculate_production_gp(production):
    if production:
        production_items = ProductionItem.objects.filter(production=production).select_related('dish')
        total_dish_revenue = calculate_total_dish_revenue(production_items)
        total_dish_cost = calculate_total_dish_cost(production_items)
        return round((total_dish_revenue - total_dish_cost) / total_dish_revenue * 100, 2) if total_dish_revenue else 0
    return 0

@register.filter
def calculate_today_sale(plan):
    sales = Sale.objects.filter(date=datetime.now().date(), void=False, branch=plan.branch)
    if sales:
        return round(sum(item.quantity * Decimal(item.price) if item.price else 0 for item in sales), 2)
    return 0

@register.filter
def calculate_planned_cost(plan):
    if plan:
        production_ing_items = ProductionIngredients.objects.filter(production=plan).select_related('ingredient')
        return round(sum(item.ingredient.cost * Decimal(item.quantity) if item.quantity else 0 for item in production_ing_items), 2)
    return 0

@register.filter
def calculate_actual_cost(plan):
    if plan:
        production_ing_items = ProductionIngredients.objects.filter(production=plan).select_related('ingredient')
        return round(sum(item.ingredient.cost * Decimal(item.actual_quantity) if item.actual_quantity else 0 for item in production_ing_items), 2)
    return 0

@register.filter
def calculate_varience(plan):
    if plan:
        return calculate_actual_cost(plan) - calculate_planned_cost(plan)
    return 0