from django.core.management.base import BaseCommand
from inventory.models import Dish, Meal  
from users.models import Branch

class Command(BaseCommand):
    help = "Copy all meals and dishes from one branch to another"

    def add_arguments(self, parser):
        parser.add_argument('--from', type=int, required=True, help='Source branch ID')
        parser.add_argument('--to', type=int, required=True, help='Destination branch ID')

    def handle(self, *args, **options):
        from_branch_id = options['from']
        to_branch_id = options['to']

        try:
            from_branch = Branch.objects.get(id=from_branch_id)
            to_branch = Branch.objects.get(id=to_branch_id)
        except Branch.DoesNotExist:
            self.stdout.write(self.style.ERROR("Invalid branch ID"))
            return

        # ----------------------
        # COPY DISHES
        # ----------------------
        self.stdout.write(self.style.WARNING(f"Copying dishes from {from_branch} → {to_branch} ..."))
        dish_mapping = {}

        for dish in Dish.objects.filter(branch=from_branch):
            new_dish = Dish.objects.create(
                branch=to_branch,
                name=dish.name,
                portion_multiplier=dish.portion_multiplier,
                price=dish.price,
                cost=dish.cost,
                category=dish.category,
                dish=dish.dish,
                low_stock=dish.low_stock,
                image=dish.image
            )
            dish_mapping[dish.id] = new_dish
        self.stdout.write(self.style.SUCCESS(f"Copied {len(dish_mapping)} dishes."))

        # ----------------------
        # COPY MEALS
        # ----------------------
        self.stdout.write(self.style.WARNING(f"Copying meals from {from_branch} → {to_branch} ..."))
        meal_count = 0
        for meal in Meal.objects.filter(branch=from_branch):
            new_meal = Meal.objects.create(
                branch=to_branch,
                name=meal.name,
                price=meal.price,
                category=meal.category,
                deactivate=meal.deactivate,
                meal=meal.meal,
                image=meal.image
            )

            old_dishes = meal.dish.all()
            new_dishes = [dish_mapping[d.id] for d in old_dishes if d.id in dish_mapping]
            new_meal.dish.set(new_dishes)
            meal_count += 1

        self.stdout.write(self.style.SUCCESS(f"Copied {meal_count} meals successfully."))
        self.stdout.write(self.style.SUCCESS("✅ All meals and dishes copied successfully!"))
