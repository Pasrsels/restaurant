from django.core.management.base import BaseCommand
from users.models import Branch  
from inventory.models import Product

class Command(BaseCommand):
    help = "Copy all meals, dishes, and products from one branch to another"

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
            self.stdout.write(self.style.ERROR("❌ Invalid branch ID"))
            return

        self.stdout.write(self.style.WARNING(f"🚀 Copying data from '{from_branch}' → '{to_branch}' ..."))

        self.stdout.write(self.style.WARNING("Copying products..."))
        product_count = 0
        for product in Product.objects.filter(branch=from_branch):
            Product.objects.create(
                branch=to_branch,
                name=product.name,
                quantity=product.quantity,
                cost=product.cost,
                price=product.price,
                unit=product.unit,
                category=product.category,
                tax_type=product.tax_type,
                min_stock_level=product.min_stock_level,
                raw_material=product.raw_material,
                finished_product=product.finished_product,
                description=product.description,
                deactivate=product.deactivate,
                image=product.image
            )
            product_count += 1
        self.stdout.write(self.style.SUCCESS(f"✅ Copied {product_count} products."))

        self.stdout.write(self.style.SUCCESS("🎉 All meals, dishes, and products copied successfully!"))
