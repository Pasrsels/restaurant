import uuid
from django.db import models
from inventory.models import Product
from users.models import Branch, User

class TimestampModel(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta: 
        abstract = True

class Production(TimestampModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, related_name='production_production_set')
    confirm = models.BooleanField(default=False)
    plan_number = models.CharField(max_length=10, unique=True, default='')
    declared = models.BooleanField(default=False)


    def save(self, *args, **kwargs):
        if not self.plan_number:   
            self.plan_number = self.generate_production_plan_number()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_production_plan_number():
        return f'PP-{uuid.uuid4().hex[:5].upper()}'

    def __str__(self) -> str:
        return self.plan_number

class ProductionItem(TimestampModel):
    production = models.ForeignKey(Production, on_delete=models.CASCADE)
    dish = models.ForeignKey('production.Dish', on_delete=models.CASCADE)  
    actual_portions = models.FloatField(null=True, blank=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    declared = models.BooleanField(default=False)
    portions = models.FloatField(default=0, null=True)
    

    def __str__(self):
        return f'{self.production.plan_number}: {self.dish.name}'

class ProductionIngredients(models.Model):  
    production = models.ForeignKey(Production, on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Product, on_delete=models.CASCADE)
    total_quantity_per_kg = models.FloatField()
    variance_cost = models.FloatField()
    variance = models.FloatField()
    actual_quantity = models.FloatField(null=True)
    cost_per_kg = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    def __str__(self) -> str:
        return f'{self.ingredient}'
    
class Dish(TimestampModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, related_name='production_dish_set')
    name = models.CharField(max_length=100)
    portion_multiplier = models.FloatField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    category = models.CharField(
        choices=[
            ('Fast food', 'Fast food'),
            ('Meat', 'Meat'),
            ('Starch', 'Starch'),
            ('Salad', 'Salad')
        ],
        max_length=255
    )
    is_dish = models.BooleanField(default=True)
    low_stock = models.IntegerField(default=10, null=True)
    image = models.ImageField(upload_to='meal_images/', default='placeholder1.jpg', null=True)
    low_stock_time = models.ForeignKey(
        'production.MealDishLowStock',
        on_delete=models.CASCADE,
        related_name="dish_notification",
        null=True, blank=True
    )

    def __str__(self) -> str:
        return self.name

class Ingredient(TimestampModel):
    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, null=True)
    note = models.CharField(max_length=100, null=True)
    quantity = models.FloatField()
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    raw_material = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, related_name='production_ingredient_raws')

    def __str__(self) -> str:
        return self.raw_material.name if self.raw_material else 'None'


class MealCategory(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name



class Meal(TimestampModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, related_name='production_meal_set')
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0) 
    dishes = models.ManyToManyField(Dish, related_name='dishes')
    category = models.ForeignKey(MealCategory, on_delete=models.CASCADE, null=True)
    deactivate = models.BooleanField(default=False)
    is_meal = models.BooleanField(default=True) 
    image = models.ImageField(upload_to='meal_images/', default='placeholder1.jpg', null=True)
    low_stock_time = models.ForeignKey(
        'production.MealDishLowStock',
        on_delete=models.CASCADE,
        related_name='meal_notification',
        null=True, blank=True
    )

    def __str__(self) -> str:
        return self.name


class MealDishLowStock(TimestampModel):
    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, null=True)
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, null=True)
    time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    portions = models.IntegerField()

    def __str__(self):
        return f'{self.dish.name if self.dish else "No Dish"}'


class Supplies(TimestampModel):
    TYPE_CHOICES = (
        ('dish', 'Dish'),
        ('meal', 'Meal'),
    )
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, null=True, blank=True)
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, null=True, blank=True)
    item = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='production_supplies')
    quantity = models.IntegerField()

    def __str__(self):
        return f"{self.item.name} ({self.get_type_display()})"


class ProductionInventory(models.Model):  # kitchen inventory
    raw_material = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='production_productioninventories')
    quantity = models.FloatField()
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True)

    def __str__(self) -> str:
        return f'{self.raw_material}: ({self.quantity})'


class ProductionLogs(models.Model):  # kitchen inventory logs
    ACTION_CHOICES = [
        ('sale', 'Sale'),
        ('stock in', 'Stock In'),
        ('declared', 'Declared'),
        ('to production', 'To Production'),
    ]
    product = models.ForeignKey(ProductionInventory, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='production_productionlogs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity = models.FloatField()
    total_quantity = models.FloatField()
    description = models.CharField(max_length=255, null=True)


class AllocatedRawMaterials(models.Model):
    production = models.ForeignKey(Production, on_delete=models.CASCADE)
    raw_material = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='production_allocatedrawmaterials')
    remaining_quantity = models.FloatField(null=True)
    quantity = models.FloatField()

    def __str__(self) -> str:
        return f'{self.production} ({self.raw_material}: {self.quantity})'

class ProductionRawMaterialAllocation(models.Model):
    production = models.ForeignKey(Production, on_delete=models.CASCADE, null=True)
    product = models.ForeignKey('inventory.product', on_delete=models.CASCADE, related_name='production_productionrawmaterials_set')
    quantity = models.FloatField(null=True)
    expected_quantity = models.FloatField(null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, related_name='production_productionrawmaterials_set')
    
    def __str__(self) -> str:
        return self.product.name