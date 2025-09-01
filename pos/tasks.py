from celery import shared_task
from datetime import datetime, time
from inventory.models import Product

@shared_task
def lowStockNotifications(dish_name, quantity):

    current_time = datetime.now().time()

    target_time_morning = time(11,59,59)
    target_time_afternoon = time(13,30,00)
    target_time_latenoon = time(16,30,00)
    target_time_evening = time(18,00,00)

    if current_time < target_time_morning:
        notify = f'{dish_name} is low current quantity is {quantity}'

@shared_task
def updateTakeAway(jobs):
    print(jobs)
    updated_products = []
    try:
        for item in jobs:
            update_product = Product.objects.get(name=item['Product_Name'])
            update_product.quantity -= item['Quantity']
            update_product.save()
            updated_products.append(f"{update_product.name} => {update_product.quantity}")
        return f"Updated products: {', '.join(updated_products)}"
    except Exception as e:
        return str(e)