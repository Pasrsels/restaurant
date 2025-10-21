from rest_framework import serializers
from inventory.models import Product, Category, Dish, Meal
from finance.models import Sale, SaleItem

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'cost', 'quantity',
            'category', 'tax_type', 'image', 'unit'
        ]
        read_only_fields = ['id']

class DishSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dish
        fields = [
            'id', 'name', 'portion_multiplier', 'price', 'cost',
            'category', 'low_stock', 'image'
        ]
        read_only_fields = ['id']

class MealDishSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dish
        fields = ['id', 'name', 'price', 'image']
        read_only_fields = ['id']

class MealSerializer(serializers.ModelSerializer):
    dishes = MealDishSerializer(many=True, read_only=True)
    
    class Meta:
        model = Meal
        fields = ['id', 'name', 'price', 'dishes', 'image']
        read_only_fields = ['id']

class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = [
            'product', 'quantity', 'unit_price', 'total_price',
            'discount', 'tax_amount', 'notes'
        ]

class OrderSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    
    class Meta:
        model = Sale
        fields = [
            'id', 'sale_number', 'customer_name', 'customer_phone',
            'subtotal', 'tax_amount', 'discount_amount', 'total_amount',
            'payment_method', 'payment_status', 'status', 'notes',
            'items', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'sale_number', 'subtotal', 'tax_amount',
            'discount_amount', 'total_amount', 'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        request = self.context.get('request')
        
        # Calculate order totals
        subtotal = sum(
            (item['unit_price'] * item['quantity']) - item.get('discount', 0)
            for item in items_data
        )
        
        # For simplicity, using a fixed tax rate - adjust as needed
        tax_rate = 0.15  # 15% tax rate
        tax_amount = subtotal * tax_rate
        total_amount = subtotal + tax_amount
        
        # Create the sale
        sale = Sale.objects.create(
            branch=request.user.branch,
            user=request.user,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            payment_status='completed',  # Assuming immediate payment for now
            status='completed',
            **validated_data
        )
        
        # Create sale items
        for item_data in items_data:
            SaleItem.objects.create(sale=sale, **item_data)
            
            # Update product quantity if it's a product sale
            if 'product' in item_data:
                product = item_data['product']
                product.quantity -= item_data['quantity']
                product.save(update_fields=['quantity'])
        
        return sale
