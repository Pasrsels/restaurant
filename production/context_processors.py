from .models import *

def meal_categories(request):
    meal_categories = MealCategory.objects.all()
    return {'meal_categories': meal_categories}