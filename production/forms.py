from production.models import *
from django import forms

class ProductionPlanInlineForm(forms.ModelForm):
    class Meta:
        model = ProductionItem
        fields = [
            'dish', 
            'portions', 
        ]

class DishForm(forms.ModelForm):
    class Meta:
        model = Dish
        exclude = ['cost', 'dish']

class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = ['raw_material', 'quantity', 'note']

class MealForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = ['name', 'price', 'category', 'dishes', 'image']
        widgets = {
            'dish': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }

class MealCategoryForm(forms.ModelForm):
    class Meta:
        model = MealCategory
        fields = '__all__'

class ProductionInlineForm(forms.ModelForm):
    class Meta:
        model = ProductionItem
        fields = ['dish', 'portions']
        widgets = {
            'dish': forms.Select(attrs={'class': 'form-control'}),
            'portions': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }