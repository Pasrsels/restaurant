import csv
from django.core.management.base import BaseCommand
from inventory.models import Meal 

class Command(BaseCommand):
    help = "Export Meals and their related Dishes to CSV"

    def handle(self, *args, **kwargs):
        filename = "meals_export.csv"

        with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            # Write header
            writer.writerow([
                "Meal ID",
                "Meal Name",
                "Price",
                "Category",
                "Branch",
                "Dishes",
                "Deactivate",
                "Meal",
            ])

            # Write rows
            for meal in Meal.objects.all():
                dish_names = ", ".join([dish.name for dish in meal.dish.all()])
                writer.writerow([
                    meal.id,
                    meal.name,
                    meal.price,
                    meal.category.name if meal.category else "",
                    meal.branch.branch_name if meal.branch else "",
                    dish_names,
                    meal.deactivate,
                    meal.meal,
                ])

        self.stdout.write(self.style.SUCCESS(f"Export completed! File saved as {filename}"))
