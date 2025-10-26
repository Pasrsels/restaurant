import datetime
from loguru import logger
from .models import *
from inventory.models import *

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


def all_dishes_products(request):
    if request.user.is_authenticated:
        products = Product.objects.filter(branch=request.user.branch).values('id', 'name', 'cost')
        dishes = Dish.objects.filter(branch=request.user.branch).values('id', 'name', 'cost')
    else:
        products = []
        dishes = []
    return {
        "dishes": list(dishes) + list(products)
    }

def products(request):
    products = Product.objects.all()
    return {'products':products}

def categories(request):
    categories = Category.objects.all()
    return {'categories':categories}