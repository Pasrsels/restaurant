import datetime
from loguru import logger
from .models import *

def notification_processor(request):
    notifications = Notification.objects.filter(is_read=False)
    return {'notifications': notifications}

def check_list_processor(request):
    products = CheckList.objects.filter(date=datetime.datetime.today())
    non_production_products = Product.objects.filter(raw_material=False)
    
    check_list = []
    for product in non_production_products:
        if not products.filter(product=product).exists():
            check_list.append(CheckList(
                product = product,
                status = False
            ))

    CheckList.objects.bulk_create(check_list)
    
    products = CheckList.objects.filter(date=datetime.datetime.today())
    
    return {'products': products}


def all_meals_dishes(request):
    dishes = Dish.objects.all().values('id', 'name')
    return {
        "dishes": dishes
    }

def products(request):
    products = Product.objects.all()
    return {'products':products}