import pandas as pd
from django.core.management.base import BaseCommand
from inventory.models import Meal, Dish 

class Command(BaseCommand):
    help = "Attach dishes to meals from CSV"

    def handle(self, *args, **options):
        # Load the CSV that has dishes
        df = pd.read_csv("meals_export.csv")

        missing_meals = []

        for _, row in df.iterrows():
            meal_id = row["Meal ID"]
            meal_name = row["Meal Name"]
            dishes_text = row["Dishes"]

            try:
                meal = Meal.objects.get(id=meal_id)
            except Meal.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Meal ID {meal_id} ({meal_name}) not found"))
                continue

            if pd.isna(dishes_text) or str(dishes_text).strip() == "":
                missing_meals.append((meal_id, meal_name))
                continue

            # Split dishes by comma and trim spaces
            dish_names = [d.strip() for d in dishes_text.split(",")]

            for dish_name in dish_names:
                dish, created = Dish.objects.get_or_create(name=dish_name)
                meal.dish.add(dish)

            meal.save()
            self.stdout.write(self.style.SUCCESS(f"Updated meal {meal_name} with dishes: {dishes_text}"))

        # Print meals that didn’t have dishes
        if missing_meals:
            self.stdout.write("\nMeals without dishes:")
            for m_id, m_name in missing_meals:
                self.stdout.write(f"- {m_id}: {m_name}")
