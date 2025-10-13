import csv
import asyncio
import tempfile
import subprocess
from celery import shared_task
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.functional import lazy
from django.apps import apps
from loguru import logger
import json, datetime
from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum
from finance.models import Change, Sale, SaleItem, CashBook, CashierExpense
from django.db import transaction
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from finance.forms import CashUp, ChangeForm
from asgiref.sync import sync_to_async
from django.utils.timezone import localdate
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from inventory.models import (
    EndOfDayItems,
    Product, 
    Logs
)
from inventory.views import finishedProduct
from .models import SaleAuthorization
from finance.models import SaleItem, Sale
from permisions.permisions import (
    admin_required,
    sales_required
)
from django.views.decorators.cache import cache_page
import requests
import tempfile
import logging
from django.db.models import Q
from django.contrib.auth import authenticate 
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.paginator import Paginator
from users.models import User
from django.core.mail import EmailMessage
from utils.email import EmailThread
import io
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from django.db.models import Sum
from django.contrib import messages
from .tasks import lowStockNotifications, updateTakeAway
from collections import defaultdict
from django.core.cache import cache
from inventory.forms import ProductionPlanInlineForm
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import localtime
from inventory.models import Meal, Dish, DailyLowStockFlag

today = localdate()

@csrf_exempt
def lowStockNotification(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        logger.info(data)
        return JsonResponse({'success': True, 'data': data})

@login_required
def pos(request):
    form = ProductionPlanInlineForm()
    low_stock_qs = DailyLowStockFlag.objects.filter(is_active=True)
    low_stock = []
    for flag in low_stock_qs:
        low_stock.append({
            'meal': {'name': flag.meal.name} if flag.meal else None,
            'dish': {'name': flag.dish.name} if flag.dish else None,
            'message': flag.message if hasattr(flag, 'message') else '',
            'threshold': flag.threshold if hasattr(flag, 'threshold') else '',
            'current_portions': flag.current_portions if hasattr(flag, 'current_portions') else '',
        })
        
    meals = Meal.objects.filter(deactivate=False, branch = request.user.branch).select_related('branch', 'category')
    products = Product.objects.filter(raw_material=False, branch = request.user.branch).select_related('branch', 'category')
    dishes = Dish.objects.filter(branch = request.user.branch).select_related('branch')

    meal_data = [
        {
            'image': meal.image.url if meal.image else '',
            'name':meal.name,
            'price':meal.price,
            'category':meal.category.name,
            'meal':meal.meal,
            'id':f'm-{meal.id}'
        }
        for meal in meals
    ]

    product_data = [
        {
            'image': product.image.url if product.image else '',
            'name':product.name,
            'price':product.price,
            'finished_product':product.finished_product,
            'id':f'p-{product.id}'
        }
        for product in products
    ]

    dish_data = [
        {
            'image': dish.image.url if dish.image else '',
            'name':dish.name,
            'price':dish.price,
            'dish':dish.dish,
            'id':f'd-{dish.id}'
        }
        for dish in dishes
    ]
    
    combined_items = meal_data + product_data + dish_data

    data = {
        'items': combined_items
    }

    return render(request, 'pos/pos.html', {
        'form': form,
        'low_stocks': low_stock,
        'data': data
    })

@login_required
def dashboard(request):
    return render(request, 'dashboard.html')
    
@login_required
def check_authorization(request):
    try:
        check_status = SaleAuthorization.objects.filter(auth_date = datetime.date.today(), auth_granted = True)
        if check_status:
            return JsonResponse({'success':True}, status = 200)
        return JsonResponse({'success':False}, status = 404)
    except Exception as e:
        return JsonResponse({'success':False, 'message':f"{e}"}, status = 505)

@login_required
def product_meal_json(request):
    if request.method == 'GET':
        
        meals = Meal.objects.filter(deactivate=False, branch = request.user.branch)
        products = Product.objects.filter(raw_material=False, branch = request.user.branch).values('id', 'name', 'price', 'finished_product', 'image')
        dishes = Dish.objects.filter(branch = request.user.branch).values('id', 'name', 'price', 'dish', 'image')
	
        meal_data = [
            {
                'image': meal.image.url.replace('/media/', '', 1) if meal.image else '',
                'name':meal.name,
                'price':meal.price,
                'category':meal.category.name,
                'meal':meal.meal,
                'id':f'm-{meal.id}'
            }
            for meal in meals
        ]

        product_data = [
            {
                'image': product['image'],
                'name':product['name'],
                'price':product['price'],
                'finished_product':product['finished_product'],
                'id':f'p-{product['id']}'
            }
            for product in products
        ]

        dish_data = [
            {
                'image': dish['image'],
                'name':dish['name'],
                'price':dish['price'],
                'dish':dish['dish'],
                'id':f'd-{dish['id']}'
            }
            for dish in dishes
        ]

        combined_items = meal_data + product_data + dish_data

        data = {
            'items': combined_items
        }
    
        return JsonResponse(data)

    return JsonResponse('Invalid request', status=500)

@login_required
def sales_list(request):
    today = datetime.datetime.today()
    sales = Sale.objects.filter(date=today, branch = request.user.branch)
    
    total_sales = sum(sale.total_amount for sale in sales) 
    
    sales_data = list(sales.values())
    data = {
        'sales': sales_data,
        'total_sales': total_sales
    }
    return JsonResponse(data)


@login_required
def meal_detail_json(request, meal_id):
    if request.method == 'POST':
        try:
            meal = Meal.objects.filter(id=meal_id, branch = request.user.branch)
            meal_data = {
                'id':meal.id,
                'name':meal.name,
                'price':meal.price
            }
        except Meal.DoesNotExist:
            return JsonResponse({'success':False, 'message':f'meal with ID: {meal_id} doesn\'t exists'})
        
        return JsonResponse({'success':True, 'data': meal_data})
    

def create_client_change(client_data, receipt_number, cashier, sale):
    logger.info(f'client name: {client_data}')

    Change.objects.create(
        sale=sale,
        name=client_data.get('name'),
        phonenumber=client_data.get('phonenumber'),
        receipt_number=receipt_number,
        amount=client_data.get('balance'),
        collected=False,
        claimed=False,
        cashier=cashier
    )
    
    logger.success(f'Change created for client: {client_data.get('name')}')

def _process_sale_data(sale_data, user):
    with transaction.atomic():
        items = sale_data['items']
        staff = sale_data['staff']
        change_data = sale_data.get('change_data')
        order_type = sale_data['order_type']
        cash_type = sale_data['cash_type']
        received_amount = sale_data.get('received_amount')

        sub_total = sum(item['price'] * item['quantity'] for item in items)
        tax = sub_total * 0.15
        total_amount = sub_total
        balance = 0
        
        if change_data:
            change_data = change_data[0]
            balance = change_data['balance']

        if staff:
            received_amount = 0.00

        sale = Sale.objects.create(
            branch=user.branch,
            total_amount=total_amount,
            tax=tax,
            sub_total=sub_total,
            cashier=user,
            staff=staff,
            change=balance,
            amount_paid=received_amount,
            cash_type=cash_type
        )

        product = None
        for item in items:
            if not item['type']:
                meal = None
                dish = None
                if item.get('meal'):
                    meal_id = item['meal_id'].split('-')[1]
                    meal = get_object_or_404(Meal, id=meal_id, branch=user.branch)
                elif item.get('dish'):
                    dish_id = item['meal_id'].split('-')[1]
                    dish = get_object_or_404(Dish, id=dish_id, branch=user.branch)

                sale_item = SaleItem.objects.create(
                    sale=sale,
                    quantity=item['quantity'],
                    price=meal.price if meal else dish.price,
                )
                if meal:
                    sale_item.meal = meal
                elif dish:
                    sale_item.dish = dish
                    
                sale_item.save()
                
                # _process_supplies(dish, meal, user)
                
                # _process_log(product=product, user=user, sale=sale, quantity=sale_item.quantity, total_quantity=product.quantity)
                
            else:
                product_id = item['meal_id'].split('-')[1]
                product = get_object_or_404(Product, id=product_id, branch=user.branch)
                product.quantity -= item['quantity']
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=item['quantity'],
                    price=product.price,
                )
                product.save()
     
                _process_log(product,user, sale, sale_item.quantity)

        CashBook.objects.create(
            branch=user.branch,
            sale=sale,
            amount=sale.total_amount,
            debit=True,
            description=f'Sale (Receipt number: {sale.receipt_number})'
        )
        
        if change_data:
            create_client_change(change_data, sale.receipt_number, sale.cashier, sale)

        return sale
    

# def _process_supplies(dish, meal, user):
#     from inventory.models import Supplies

#     supplies = Supplies.objects.filter(dish=dish) if dish else Supplies.objects.filter(meal=meal)
    
#     with transaction.atomic():
    
#         for supply in supplies:
#             product = supply.item
#             product.quantity -= supply.quantity
#             product.save()
            
#             logger.info(f'{supply.item} deducted {supply.quantity}')
            
#             Logs.objects.create(
#                 branch=user.branch,
#                 product=product,
#                 user=user,
#                 quantity=supply.quantity,
#                 total_quantity=product.quantity,
#                 description="Sale",
#                 action='Sale'
#             )
            
def _process_log(product, user, sale, quantity):
    """Record a sale log for finished products with linkage to the sale for reversals."""
    try:
        Logs.objects.create(
            branch=user.branch,
            sale=sale,
            product=product,
            user=user,
            quantity=quantity,
            total_quantity=product.quantity if product else 0,
            description="Sale",
            action='sale'
        )
    except Exception as e:
        logger.error(f"Failed to create sale log: {e}")

def check_low_stock(meal=None, dish=None, current_portions=0):
    """
        Check and update low stock status for a meal or dish.
        Returns a dictionary with the status and saves it in DailyLowStockFlag.
    """
    if not meal and not dish:
        return {
            "is_low_stock": False,
            "message": "No meal or dish provided",
            "threshold": None
        }

    now_time = localtime(datetime.now()).time()
    today = localtime(datetime.now()).date()

    low_stock_entries = MealDishLowStock.objects.filter(
        meal=meal if meal else None,
        dish=dish if dish else None
    )

    for entry in low_stock_entries:
        if entry.from_time <= now_time <= entry.to_time:
            if current_portions <= entry.portions:
                flag, created = DailyLowStockFlag.objects.get_or_create(
                    dish=dish,
                    meal=meal,
                    date=today,
                    defaults={
                        "time_detected": now_time,
                        "current_portions": current_portions,
                        "threshold": entry.portions,
                        "is_active": True
                    }
                )

                if not created:
                    flag.current_portions = current_portions
                    flag.is_active = True
                    flag.save()

                return {
                    "is_low_stock": True,
                    "message": f"Low stock: Portions ({current_portions}) ≤ Threshold ({entry.portions}).",
                    "threshold": entry.portions,
                    "from_time": entry.from_time,
                    "to_time": entry.to_time
                }
                
    DailyLowStockFlag.objects.filter(
        dish=dish,
        meal=meal,
        date=today,
        is_active=True
    ).update(is_active=False)

    return {
        "is_low_stock": False,
        "message": "Stock level is sufficient.",
        "threshold": None
    }

@login_required
def remove_duplicates(request):
    transactions = Change.objects.filter(timestamp__date=datetime.datetime.today()) 

    grouped = defaultdict(list)
    for tx in transactions:
        key = (tx.name.strip().lower(), float(tx.amount))
        grouped[key].append(tx)

    removed_count = 0
    kept_transactions = []  

    for key, tx_list in grouped.items():
        collected_txs = [tx for tx in tx_list if tx.collected]
        not_collected_txs = [tx for tx in tx_list if not tx.collected]

        if collected_txs:
            to_keep = collected_txs[0]
        else:
            to_keep = not_collected_txs[0]

        kept_transactions.append(to_keep) 

        for tx in tx_list:
            if tx.id != to_keep.id:
                tx.delete()
                removed_count += 1

    
@login_required
def process_sale(request):
    if request.method == 'POST':
        try:
            sale_data = json.loads(request.body)
            logger.info(f'Sale data received: {sale_data}')
            sale = _process_sale_data(sale_data, request.user)

            data = {
                'receipt_number': sale.receipt_number,
                'date': str(localdate()),
                'time': timezone.localtime().strftime("%H:%M:%S"),
                'cashier': f'{request.user.first_name} {request.user.last_name}',
                'receipt_number': sale.receipt_number,
                'total_amount': sale.total_amount,
                'tax': sale.tax,
                'sub_total': sale.sub_total,
                'received_amount': sale_data.get('received_amount'),
                'change': sale_data.get('received_amount') - sale.total_amount,
                'items': list(SaleItem.objects.filter(sale=sale).values('quantity', 'price', 'meal__name', 'dish__name', 'product__name'))
            }

            remove_duplicates(request)
            
            logger.success(f'sale successfully recorded: {sale}')
            
            return JsonResponse({'success': True, 'data': data}, status=201)
        except Exception as e:
            logger.error(f'Error processing sale: {str(e)}')
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

def get_csrf_token(request):
    return JsonResponse({'csrfToken': request.COOKIES.get('csrftoken')})

@login_required
def sync_collections(request):
    if request.method == 'POST':
        try:
            pending_collections = json.loads(request.body)
            for collection_data in pending_collections:
                change_id = collection_data.get('change_id')
                amount = Decimal(collection_data.get('amount'))

                change = Change.objects.get(id=change_id, sale__branch=request.user.branch)
                cashier = request.user

                if amount == change.amount:
                    change.collected = True
                    change.cashier_give = cashier
                elif amount < change.amount:
                    change.amount -= Decimal(amount)
                    change.cashier_give = cashier
                else:
                    return JsonResponse({'success':False, 'message':'Amount collected is more than the change amount'}, status=400)
                change.save()
            return JsonResponse({'success': True}, status=200)
        except Exception as e:
            logger.error(f'Error syncing collections: {str(e)}')
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

@login_required
def deduct_current_production_plan(request, meal, dish, product, quantity, staff):
    pass

@login_required
def change_list(request):
    filter_option = request.GET.get('filter', 'today')
    now = timezone.now()  
    
    if filter_option == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif filter_option == 'yesterday':
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif filter_option == 'this_week':
        start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif filter_option == 'this_month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end_date = now.replace(day=31, hour=23, minute=59, second=59, microsecond=999999)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = (next_month - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)
    elif filter_option == 'last_month':
        first_day_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_prev_month = first_day_current_month - timedelta(days=1)
        start_date = last_day_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = last_day_prev_month.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif filter_option == 'this_year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif filter_option == 'custom':
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            if timezone.is_aware(now):
                start_date = timezone.make_aware(start_date.replace(hour=0, minute=0, second=0))
                end_date = timezone.make_aware(end_date.replace(hour=23, minute=59, second=59))
            else:
                start_date = start_date.replace(hour=0, minute=0, second=0)
                end_date = end_date.replace(hour=23, minute=59, second=59)
        else:
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
    else:
        start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now

    changes = Change.objects.filter(
        timestamp__gte=start_date,
        timestamp__lte=end_date,
        sale__branch=request.user.branch
    ).order_by('-timestamp')

    change_total = changes.aggregate(total=Sum('amount'))['total'] or 0
    change_collected_total = changes.filter(collected=True).aggregate(total=Sum('amount'))['total'] or 0
    change_uncollected_total = changes.filter(collected=False).aggregate(total=Sum('amount'))['total'] or 0
    
    paginator = Paginator(changes, 10000) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_change_amount = change_uncollected_total

    return render(
        request,
        'finance/change_list.html',
        {
            'filter_option': filter_option,
            'page_obj': page_obj,
            'end_date': end_date,
            'start_date': start_date,
            'total': total_change_amount,
            'change_total': change_total,
            'change_collected_total': change_collected_total,
            'change_uncollected_total': change_uncollected_total
        }
    )

@login_required
def change_data(request):
    data = json.loads(request.body)
    name = data.get('name').strip().lower()

    name = name.strip().lower() if name else ''

    logger.info(f'looking for change(s) data for: {name}')
    
    changes = Change.objects.filter(
        Q(name__icontains=name) | 
        Q(receipt_number__icontains=name), 
        collected=False
    ).select_related(
        'branch', 'cashier', 'cashier_give'
    ).values()

    return JsonResponse({'success':True, 'data':list(changes)})

@login_required
def download_change_report(request):
    filter_option = request.GET.get('filter', 'this_week')
    now = datetime.datetime.now()
    end_date = now
    
    if filter_option == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_week':
        start_date = now - timedelta(days=now.weekday())
    elif filter_option == 'yesterday':
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_month':
        start_date = now.replace(day=1)
    elif filter_option == 'last_month':
        start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif filter_option == 'this_year':
        start_date = now.replace(month=1, day=1)
    elif filter_option == 'custom':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    else:
        start_date = now - timedelta(days=now.weekday())
        end_date = now

    changes = Change.objects.filter(timestamp__gte=start_date, timestamp__lte=end_date, sale__branch = request.user.branch).order_by('timestamp')
    
    # Create a CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cashbook_report_{filter_option}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Name', 'Amount', 'Collected', 'Claimed', 'Balance'])

    balance = 0  
    for change in changes:
        if not change.collected:
            balance += change.amount

        writer.writerow([
            change.timestamp,
            change.name,
            change.amount,
            'collected' if change.collected else 'not collected',
            'claimed' if change.claimed else 'not claimed',
            balance,
        ])

    return response


@login_required
def create_change(request):
    #payload 
    """
        name:str,
        phonenumber:str,
        amount:float,
        receipt_number:str
    """
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            name = data.get('name')
            phonenumber = data.get('phonenumber')
            amount = Decimal(data.get('amount'))
            receipt_number = data.get('receipt_number')
            
            # validation
            if Change.objects.filter(receipt_number=receipt_number, sale__branch = request.user.branch).exists():
                return JsonResponse({'success':False, 'message':f'Change with receipt number: {receipt_number} exists.'}, status=400)
            
            Change.objects.create(
                name=name,
                phonenumber=phonenumber,
                amount=amount,
                receipt_number=receipt_number,
                cashier=request.user,
                collected=False,
                claimed=False,
            )
            return JsonResponse({'success':True}, status=201)
        except Exception as e:
            return JsonResponse({'success':False, 'message':f'{e}'}, status=400)
    return JsonResponse({'success':False, 'message':'Invalid request'}, status=405)

@login_required
def collect_change(request):
    # payload
    """
        change_id:id,
        amount:float
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            change_id = data.get('change_id')
            amount = Decimal(data.get('amount'))
            cashier_id = request.user.id
            
            change = Change.objects.get(id=change_id, sale__branch = request.user.branch)
            cashier = User.objects.get(id = cashier_id)

            if amount > change.amount:
                return JsonResponse({'success':False, 'message': 'Amount cant be be more than the change amount'})

            new_collected = change.amount_collected + amount
            new_balance = change.amount - new_collected

            logger.info(change.amount_collected)

            if new_balance < 0:
                return JsonResponse({'success': False, 'message': 'Amount collected exceeds the total change amount'}, status=400)

            change.amount_collected = new_collected
            change.balance = new_balance
            change.cashier_give = cashier
            change.data_collected = datetime.datetime.now()
            
            if new_balance == 0:
                change.collected = True
            
            change.save()
            
            return JsonResponse({
                'success': True, 
                'amount_collected': str(change.amount_collected),
                'balance': str(change.balance),
                'collected': change.collected
            }, status=200)
        except Exception as e:
            logger.error(f'Error recording change: {e}')
            return JsonResponse({'success':False, 'message':f'{e}'}, status=400)
    return JsonResponse({'success':False, 'message':'Invalid request'}, status=405)

@login_required
def void_sales(request, user_id):
    if request.method == 'GET':
        sales = Sale.objects.filter(date=timezone.now(), branch = request.user.branch).order_by('-date')
        
        sale_items = SaleItem.objects.filter(sale__date=timezone.now(), sale__branch = request.user.branch)
    
        return render (request, 'pos/void_sales.html', {
            'sales':sales,
            'sale_items':sale_items,
            'user_id':user_id
        })
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            logger.info(f'Sales data for voiding: {data}')


            sale_id = data['sale_id']
            sale = get_object_or_404(Sale, id=sale_id, branch = request.user.branch)
            items = SaleItem.objects.filter(sale=sale)

            if sale.void:
                return JsonResponse({'success': False, 'message': 'Sale is already voided'}, status=400)

            with transaction.atomic():
                sale.void = True
                sale.save()

                logger.info(f'Sale marked as voided: {sale}')
                # for item in items:
                #     product = item.product or item.meal or item.dish

                #     if product:
                #         if isinstance(product, Product):

                #             product.quantity += item.quantity
                #             product.save()

                #             logger.info(f'Reverted product stock: {product}')

                #         elif isinstance(product, ProductionItems):
                #             product.portions_sold -= item.quantity
                #             product.left_overs += item.quantity
                #             product.save()

                #             logger.info(f'Reverted production item: {product}')

                #     item.delete()

                #     logger.info(f'Deleted sale item: {item}')
                
                change = Change.objects.filter(sale=sale).first()
                if change:
                    change.delete()
                    logger.info(f'Reverted cashbook entry: {change}')

                # Reverse the logs related to the sale
             
                logs = Logs.objects.filter(sale=sale)
                logs.delete()
                logger.info(f'Reverted Sale log: {sale.id}')

                # Revert cash book entry if it exists
                cashbook_entry = CashBook.objects.filter(sale=sale).first()
                if cashbook_entry:
                    cashbook_entry.delete()
                    logger.info(f'Reverted cashbook entry for sale: {sale.id}')

                # Return the response indicating success
                return JsonResponse({'success': True, 'message': 'Sale has been voided successfully'}, status=200)

        except Exception as e:
            logger.error(f'Error processing void transaction: {str(e)}')
            return JsonResponse({'success': True, 'message': f'{e}'}, status=400)


@login_required
def void_authenticate(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            print(data)

            username = data.get("username")
            password = data.get("password")

            if not username or not password:
                return JsonResponse({"success": False, "message": "Username and password are required."}, status=400)
            
            user = User.objects.filter(username=username).first()
            if user and user.role.lower() in ['admin', 'accountant', 'supervisor', 'manager', 'owner', 'sales']:
                return JsonResponse({"success": True, 'role': user.role, "message": "Authentication successful.", "user_id":user.id}, status=200)

        except Exception as e:
            logger.error(f'Error authenticating user: {user.username} -> {e}')
            return JsonResponse({"success": False, "message": f"An error occurred: {str(e)}"}, status=500)
        
@login_required
def cash_up(request, cashier_id):
    logger.info(f'Cash up requested for cashier_id: {cashier_id} by user: {request.user.username}')

    today = datetime.datetime.today().date()
    yesterday = today - timedelta(days=1)
    
    if request.method == 'GET':
        try:
            cash_in_hand = 0
        
            try:
                cashier = User.objects.get(id=cashier_id)
                logger.info(f'Found cashier: {cashier.username}')
            except User.DoesNotExist:
                logger.error(f'Cashier with id {cashier_id} does not exist')
                return JsonResponse({'success': False, 'message': 'Cashier not found'}, status=404)
                
            if not request.user.branch:
                logger.error('Request user has no branch assigned')
                return JsonResponse({'success': False, 'message': 'User has no branch assigned'}, status=400)

            sales = Sale.objects.filter(cashier__id=cashier_id, date=datetime.datetime.today(), void=False, branch=request.user.branch).values('total_amount', 'cash_type', 'staff')
            sales_items = SaleItem.objects.filter(sale__cashier__id=cashier_id, sale__date=datetime.datetime.today(), sale__branch=request.user.branch)
            void_sales = Sale.objects.filter(cashier__id=cashier_id, date=datetime.datetime.today(), void=True, branch=request.user.branch).values('total_amount')

            sales_dict = {}
            staff_meals_dict = {}
            void_sales_dict = {}

            total_summary_sales = 0
            total_staff_summary_sales = 0
            sales_summary = defaultdict(lambda: {'price': 0, 'quantity':0})
            staff_sales_summary = defaultdict(lambda: {'price': 0, 'quantity':0})
        
            for sale in sales_items.filter(sale__staff=False):
                item = sale.meal or sale.product or sale.dish

                if item:
                    key = f"{item.name}"
                    sales_summary[key]['price'] = round(sale.price, 2)  # revisit
                    sales_summary[key]['quantity'] += sale.quantity
                    total_summary_sales += round(sale.price * sale.quantity, 2)
            
            for sale in sales_items.filter(sale__staff=True):
                item = sale.meal or sale.product or sale.dish

                if item:
                    key = f"{item.name}"
                    staff_sales_summary[key]['price'] = round(sale.price, 2)  # revisit
                    staff_sales_summary[key]['quantity'] += sale.quantity
                    total_staff_summary_sales += round(sale.price * sale.quantity, 2)

            # to be optimised
            for items in sales_items.filter(sale__staff=False):
                if items.dish:
                    name = [{'Name': items.dish.name, 'Price': items.dish.price}]
                elif items.product:
                    name = [{'Name': items.product.name, 'Price': items.product.price}]
                elif items.meal:
                    name = [{'Name': dish.name, 'Price': dish.price} for dish in items.meal.dish.all()]
                else:
                    name = None

                if name:
                    for item in name:
                        dish_name = item['Name']
                        dish_price = item['Price']

                        if not items.sale.void and not items.sale.staff:
                            if dish_name in sales_dict:
                                sales_dict[dish_name]['Quantity'] += items.quantity
                                sales_dict[dish_name]['Total'] += items.quantity * dish_price
                            else:
                                sales_dict[dish_name] = {
                                    'Name': dish_name,
                                    'Quantity': items.quantity,
                                    'Price': dish_price,
                                    'Total': items.quantity * dish_price
                                }
                        elif items.sale.staff:
                            if dish_name in staff_meals_dict:
                                staff_meals_dict[dish_name]['Quantity'] += items.quantity
                                staff_meals_dict[dish_name]['Total'] += items.quantity * dish_price
                            else:
                                staff_meals_dict[dish_name] = {
                                    'Name': dish_name,
                                    'Quantity': items.quantity,
                                    'Price': dish_price,
                                    'Total': items.quantity * dish_price
                                }
                        elif items.sale.void:
                            if dish_name in void_sales_dict:
                                void_sales_dict[dish_name]['Quantity'] += items.quantity
                                void_sales_dict[dish_name]['Total'] += items.quantity * dish_price
                            else:
                                void_sales_dict[dish_name] = {
                                    'Name': dish_name,
                                    'Quantity': items.quantity,
                                    'Price': dish_price,
                                    'Total': items.quantity * dish_price
                                }

            sales_portions_list = list(sales_dict.values())
            staff_meals_portions_list = list(staff_meals_dict.values())
            void_sales_portions_list = list(void_sales_dict.values())
            
            sale_total = 0
            staff_total = 0
            eco_cash_total = 0
            eco_cash_tax = 0

            for items in sales_portions_list:
                sale_total += items['Total']
            
            for items in staff_meals_portions_list:
                staff_total += items['Total']
            
            for items in sales:
                logger.info(items)
                if items['cash_type'] == 'eco-cash' and items['staff'] == False:
                    eco_cash_total += items['total_amount']

            logger.info(f'Eco cash total: {eco_cash_total}')

            eco_cash_tax = 0.00
            logger.info(f'Eco cash tax: {eco_cash_tax}')
            variance_list = []

            eod_list = EndOfDayItems.objects.filter(end_of_day__date=datetime.datetime.today(), end_of_day__branch=request.user.branch).values(
                'dish_name',
                'wastage',
                'leftovers',
                'total_sold',
                'expected',
            )

            change = Change.objects.filter(
                cashier__id=cashier_id,
                timestamp__date=datetime.datetime.today(),
                sale__branch=request.user.branch
            ).values('amount')
            
            accumulated_change = Change.objects.filter(
                cashier__id=cashier_id,
                collected=False,
                timestamp__date=datetime.datetime.today(),
                sale__branch=request.user.branch
            )
 
            previous_change = Change.objects.filter(
                cashier__id=cashier_id,
                collected=True,
                date_collected=datetime.datetime.today(),
                sale__branch=request.user.branch
            ).select_related(
                'cashier'
            ).values('amount')

            expenses = CashierExpense.objects.filter(
                cashier__id=cashier_id,
                date=datetime.datetime.today(),
                branch=request.user.branch
            )
            
            expenses_list = []
            for item in expenses:
                name = item.name
                if name:
                    expenses_list.append({'Name': item.name, 'Amount': item.amount})
            
            total_sales = sum(sale['total_amount'] for sale in sales if not sale['staff'])
            total_staff_sales = sum(sale['total_amount'] for sale in sales if sale['staff'])
            total_void_sales = sum(void_sale['total_amount'] for void_sale in void_sales)
            total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
            total_change = accumulated_change.aggregate(Sum('amount'))['amount__sum'] or 0

            collected_changes = Change.objects.filter(
                cashier__id=cashier_id,
                collected=True,
                data_collected=datetime.datetime.today(),
                sale__branch=request.user.branch
            ).exclude(
                cashier__id=cashier_id
            ).aggregate(Sum('amount_collected'))['amount_collected__sum'] or 0

            cashier_partially_collected_changes = Change.objects.filter(
                timestamp__date=datetime.datetime.today(),
                cashier__id=cashier_id,
                collected=False,
                balance__gt=0,
                sale__branch=request.user.branch
            ).aggregate(Sum('balance'))['balance__sum'] or 0

            cashier_self_collected = Change.objects.filter(
                cashier__id=cashier_id,
                collected=True,
                sale__branch=request.user.branch,
                timestamp__date=datetime.datetime.today(),
                timestamp__date__lt=datetime.datetime.today()
            ).aggregate(Sum('amount_collected'))['amount_collected__sum'] or 0

            logger.info(f'Collected changes from others: {collected_changes}')
            logger.info(f'Partially collected changes by cashier: {cashier_partially_collected_changes}')

            total_collected_change = collected_changes + cashier_partially_collected_changes 
            collected_change = total_collected_change

            uncollected_change = Change.objects.filter(
                timestamp__date=datetime.datetime.today(),
                cashier__id=cashier_id,
                collected=False,
                amount_collected=0,
                sale__branch=request.user.branch
            ).aggregate(Sum('amount'))['amount__sum'] or 0

            logger.info(f'Uncollected changes by cashier: {uncollected_change}')
            
            cash_in_hand = total_sales - total_expenses - total_void_sales - collected_changes + uncollected_change + cashier_partially_collected_changes 
            uncollected_change = uncollected_change + cashier_partially_collected_changes
            
            cashier = User.objects.get(id=cashier_id)

            logger.info(f'Sales totals: total: {total_sales}, staff_sales: {total_staff_sales}')

            CashUp.objects.create(
                branch=request.user.branch,
                cashier=cashier,
                # cashed_amount=cashed_amount,
                void_amount=total_void_sales,
                sales=total_sales,
                change=collected_change,
                user=request.user,
                expenses=total_expenses,
                status=False,
                cashed=False,
            )

            finished_product = finishedProduct(cashier_id)

            data = {
                "total_sales": total_sales,
                'sales_portions': sales_portions_list,
                'void_sales_portions': void_sales_portions_list,
                'staff_meal_portions': staff_meals_portions_list,
                'previous_change_given': [],
                'variance': list(eod_list),
                'expense': expenses_list,
                'total_expenses': total_expenses,
                'total_change': round(uncollected_change, 2),
                'total_accumulated_change': uncollected_change,
                'cash_in_hand': round(cash_in_hand, 2),
                'sales_total': sale_total,
                'staff_total': staff_total,
                'finished_product': finished_product,
                'sales_summary': sales_summary,
                'total_summary_sales': total_summary_sales,
                'staff_sales_summary': staff_sales_summary,
                'eco_cash_total': eco_cash_total,
                'eco_cash_tax': Decimal(eco_cash_tax),
                'collected_changes': float(collected_changes),
            }   

            return JsonResponse({'success': True, "data": data})
        except Exception as e:
            logger.error(f'Error in processing cashup: {e}')
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred while processing your request',
                'error': str(e)
            }, status=500)

    return JsonResponse({'success':False,'message':'Invalid request'}, status=500)

@login_required
def update_cashed_amount(request, cashup_id):

    if request.method == 'POST':
        """
            payload:{
                amount:float
            }
        """
        try:
            data = json.loads(request.body)
            amount = data.get('cashed_amount', '')

            if not amount:
                return JsonResponse({'success':False, 'message':'Please fill in the amount field'})

            with transaction.atomic():
                cash_up = CashUp.objects.select_for_update().get(id=cashup_id, branch = request.user.branch)
                cash_in_hand = cash_up.sales - cash_up.void_amount - cash_up.expenses + cash_up.change
                cash_up.cashed_amount = amount
                if cash_up.cashed_amount == cash_in_hand:
                    cash_up.status = True
                cash_up.save()

            return JsonResponse({'success':True}, status=201)

        except Exception as e:
            return JsonResponse({'success':False,'message':f'{e}'}, status=400)
        
    return JsonResponse({'success':False,'message':'Invalid request'}, status=500)

@login_required
def accountantreport(request):
    try:
        cash_in_hand = 0
        cashier_id = request.user.id
        cashier_cash = 0 

        # Get sales data
        sales = Sale.objects.filter(
            cashier__id=cashier_id, 
            date=datetime.datetime.today(), 
            void=False, 
            branch=request.user.branch, 
            staff=False
        ).values('total_amount')
        
        # Get change data
        change = Change.objects.filter(
            cashier__id=cashier_id, 
            cashier_give__id=cashier_id, 
            timestamp__date=datetime.datetime.today(), 
            collected=False, 
            sale__branch=request.user.branch
        ).values('amount')
        
        other_cashiers_change_given = Change.objects.filter(
            cashier_give__id=cashier_id, 
            collected=True, 
            sale__branch=request.user.branch
        ).exclude(cashier__id=cashier_id).values('amount')
        
        accumulated_change = Change.objects.filter(
            cashier__id=cashier_id, 
            collected=False, 
            sale__branch=request.user.branch
        ).values('amount')
        
        accumulated_change_given = Change.objects.filter(
            cashier__id=cashier_id, 
            cashier_give__id=cashier_id, 
            collected=True, 
            sale__branch=request.user.branch
        ).values('amount')
        
        expenses = CashierExpense.objects.filter(
            cashier__id=cashier_id, 
            date=datetime.datetime.today(), 
            branch=request.user.branch
        ).values('amount')
        
        void_sales = Sale.objects.filter(
            cashier__id=cashier_id, 
            date=datetime.datetime.today(), 
            void=True, 
            branch=request.user.branch
        ).values('total_amount')

        # Get staff sales
        total_staff_sales = Sale.objects.filter(
            cashier__id=cashier_id, 
            date=datetime.datetime.today(), 
            void=False, 
            branch=request.user.branch, 
            staff=True
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

        # Get declared cash if it exists
        try:
            declared_cash = LeftOvers.objects.get(
                cashier__id=cashier_id, 
                date=datetime.datetime.today(), 
                branch=request.user.branch
            )
            cashier_cash = declared_cash.cash
        except LeftOvers.DoesNotExist:
            cashier_cash = 0
        except Exception as e:
            logger.error(f'Error getting declared cash: {str(e)}')
            cashier_cash = 0

        # Calculate totals
        total_sales = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
        total_change = change.aggregate(Sum('amount'))['amount__sum'] or 0
        other_cashiers_total_change_given = other_cashiers_change_given.aggregate(Sum('amount'))['amount__sum'] or 0 
        total_accumulated_change = accumulated_change.aggregate(Sum('amount'))['amount__sum'] or 0
        total_accumulated_change_given = accumulated_change_given.aggregate(Sum('amount'))['amount__sum'] or 0
        total_void_sales = void_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        # Calculate collected changes and net change for the cashier today
        collected_changes = Change.objects.filter(
            cashier__id=cashier_id,
            timestamp__date=datetime.datetime.today(),
            collected=True,
            sale__branch=request.user.branch
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Calculate net change (total change - collected changes)
        net_change = total_change - collected_changes

        cash_in_hand = total_sales - total_expenses - total_void_sales + total_change
        
        # Log the cash in hand and cashier cash for debugging
        logger.info(f'Cash in hand: {cash_in_hand}, Cashier cash: {cashier_cash}')
        logger.info(f'Collected changes: {collected_changes}')
        
        # Return a dictionary with the results
        return {
            'success': True,
            'cash_in_hand': float(cash_in_hand) if cash_in_hand else 0,
            'cashier_cash': float(cashier_cash) if cashier_cash else 0,
            'total_sales': float(total_sales) if total_sales else 0,
            'total_expenses': float(total_expenses) if total_expenses else 0,
            'total_change': float(total_change) if total_change else 0,
            'total_void_sales': float(total_void_sales) if total_void_sales else 0,
            'total_staff_sales': float(total_staff_sales) if total_staff_sales else 0,
            'other_cashiers_total_change_given': float(other_cashiers_total_change_given) if other_cashiers_total_change_given else 0,
            'total_accumulated_change': float(total_accumulated_change) if total_accumulated_change else 0,
            'total_accumulated_change_given': float(total_accumulated_change_given) if total_accumulated_change_given else 0,
            'collected_changes': float(collected_changes) if collected_changes else 0,
        }
    
    except Exception as e:
        logger.error(f'Error in accountantreport: {str(e)}', exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'cash_in_hand': 0,
            'cashier_cash': 0,
            'total_sales': 0,
            'total_expenses': 0,
            'total_change': 0,
            'total_void_sales': 0,
            'total_staff_sales': 0,
            'other_cashiers_total_change_given': 0,
            'total_accumulated_change': 0,
            'total_accumulated_change_given': 0,
            'collected_changes': 0,
        }
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']
    
    title = Paragraph(f"Cash Up Report - {datetime.datetime.today().strftime('%Y-%m-%d')}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    cashier_info = Paragraph(f"Cashier: {cashier.first_name} {cashier.last_name}", subtitle_style)
    elements.append(cashier_info)
    elements.append(Spacer(1, 12))
    

    sales_info = Paragraph("Sales and Cash in hand Information")
    elements.append(sales_info)
    elements.append(Spacer(1, 12))

    change_for_customers = total_accumulated_change - total_accumulated_change_given

    first_data = [
        ["Item", "Amount"],
        ["Total Sales", f"${total_sales:.2f}"],
        ["Total Expenses", f"(${total_expenses:.2f})"],
        ["Total Change", f"${total_change:.2f}"],
        ["Cash in Hand", f"${cash_in_hand:.2f}"],
        ["Staff Sales", f"${total_staff_sales:.2f}"]
    ]

    second_data = [
        ['Item', 'Amount'],
        ["Accumulated Change", f"${total_accumulated_change:.2f}"],
        ["Previous Change Given", f"${total_accumulated_change_given:.2f}"],
        ["Change to be given to Customers", f'${change_for_customers:.2f} '],
        ["Other Cashier Change", f"${other_cashiers_total_change_given:.2f}"],
    ]
    
    table = Table(first_data, colWidths=[300, 100])
    change_table = Table(second_data, colWidths=[300, 100])
    
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        # ('ALIGN', (0, 1), (1, 0), 'LEFT'),
        # ('ALIGN', (0, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (1, 0), 12),
        ('BACKGROUND', (0, 1), (1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (1, -1), colors.black),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (1, -1), 10),
        ('GRID', (0, 0), (1, -1), 1, colors.black),
        ('BOTTOMPADDING', (0, 1), (1, -1), 8),
    ])

    change_table_style = TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        # ('ALIGN', (0, 1), (1, 0), 'LEFT'),
        # ('ALIGN', (0, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (1, 0), 12),
        ('BACKGROUND', (0, 1), (1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (1, -1), colors.black),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (1, -1), 10),
        ('GRID', (0, 0), (1, -1), 1, colors.black),
        ('BOTTOMPADDING', (0, 1), (1, -1), 8),
    ])
    
    
    table.setStyle(table_style)
    elements.append(table)
    
    elements.append(Spacer(1, 20))

    change_info = Paragraph("Change Information")
    elements.append(change_info)
    elements.append(Spacer(1, 12))

    change_table.setStyle(change_table_style)
    elements.append(change_table)

    elements.append(Spacer(1, 20))
    notes = Paragraph("Notes: This report was automatically generated. Please contact the finance department if you have any questions.", normal_style)
    elements.append(notes)
    
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    def send_email_with_pdf():
        cashier = User.objects.get(id=cashier_id)
        subject = 'Accountant Report'
        from_email = "Urban Eats"
        body = f"""
        Cash Up Report for Cashier: {cashier.first_name}
        
        Please find the detailed cash up report attached as a PDF.
        """
        email = EmailMessage(
            subject,
            body,
            from_email,
            ['castinamoyo@gmail.com', 'teddychinomona@gmail.com', 'mirackletec@gmail.com'],
        )
        
        email.attach(f'cashup_report_{datetime.datetime.today().strftime("%Y%m%d")}_{cashier.username}.pdf', pdf, 'application/pdf')
        
        EmailThread(email).start()
        logger.info(f'Accountant Detailed CashUp email sent with PDF attachment.')
    
    send_email_with_pdf()
    
    if request.GET.get('download', False):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=cashup_report_{datetime.datetime.today().strftime("%Y%m%d")}_{cashier.username}.pdf'
        response.write(pdf)
        return response
    
    # Get cashier object
    cashier = User.objects.get(id=cashier_id)
    
    # Calculate collected changes for the cashier today
    collected_changes_qs = Change.objects.filter(
        cashier__id=cashier_id,
        timestamp__date=datetime.datetime.today(),
        collected=True,
        sale__branch=request.user.branch
    )
    collected_changes = collected_changes_qs.aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Debug output
    print(f"Collected changes query: {collected_changes_qs.query}")
    print(f"Collected changes value: {collected_changes}")
    
    # Calculate net change
    net_change = total_change - collected_changes
    
    # Get declared cash
    try:
        declared_cash = LeftOvers.objects.get(
            cashier__id=cashier_id,
            date=datetime.datetime.today(),
            branch=request.user.branch
        )
        cashier_cash = declared_cash.cash
    except (LeftOvers.DoesNotExist, Exception):
        cashier_cash = 0
    
    # Calculate cash in hand
    cash_in_hand = total_sales - total_expenses - total_void_sales + total_change
    
    return render(request, 'accountant_cashup_report.html', {
        'cash_up_data': {
            'date': datetime.datetime.today(),
                'total_sales': total_sales,
                'total_staff_sales': total_staff_sales,
                'total_void_sales': total_void_sales,
                'total_expenses': total_expenses,
                'collected_changes': collected_changes,
            'collected_changes': collected_changes,
            'net_change': net_change,
            'accumulative_change': total_accumulated_change,
            'previous_change_given': total_accumulated_change_given,
            'cash_in_hand': cash_in_hand,
            'declared_cash': cashier_cash,
            'variance': cash_in_hand - cashier_cash,
            'other_cashier_change': other_cashiers_total_change_given,
            'total_void_sales': total_void_sales,
        },
        'pdf_available': True,
        'cashier': cashier
    })

# def adminreport(request):

#     cashier_id = request.user.id
#     cash_in_hand = 0

#     sales = Sale.objects.filter(cashier__id=cashier_id, date=datetime.datetime.today(), void=False).values('total_amount')
#     total_sales = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0

#     leftover_stuff = LeftOvers.objects.filter(date = datetime.datetime.today()).values('total_amount')
#     total_leftovers = leftover_stuff.aggregate(Sum('total_amount'))['total_amount__sum'] or 0

#     try:
#         declared_cash = LeftOvers.objects.get(cashier__id = cashier_id, date = datetime.datetime.today())
#         cashier_cash = declared_cash.cash
#     except Exception as e:
#         cashier_cash = 0

#     change = Change.objects.filter(cashier__id=cashier_id, timestamp__date=datetime.datetime.today(), collected=False).values('amount')
#     total_change = change.aggregate(Sum('amount'))['amount__sum'] or 0

#     expenses = CashierExpense.objects.filter(cashier__id=cashier_id, date=datetime.datetime.today()).values('amount')
#     total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0


#     sale_items_list = []
#     sale_items = SaleItem.objects.filter(sale__void = False, time = datetime.datetime.today()).values('dish__name', 'dish__price', 'product__name', 'product__price', 'quantity')

#     for items in sale_items:
#         sale_items_list.append(
#             items
#         )
    
#     sale_items_dict = {}
#     for items in sale_items_list:
#         item_name = items['dish_name'] or items['product__name']

#         if item_name in sale_items_dict:
#             sale_items_dict[item_name]['quantity'] += items['quantity']
#             sale_items_dict[item_name]['price'] += items['price']
#         else:
#             sale_items_dict[item_name] = item_name
#             sale_items_dict[item_name]['quantity'] = items['quantity']
#             sale_items_dict[item_name]['price'] = items['dish_price'] or items['product_price']
    
#     leftover_list = []
#     leftover_items = LeftOvers.objects.filter(date = datetime.datetime.today()).values('dish__name', 'dish__price', 'product__name', 'product__price', 'quantity')

#     for items in leftover_items:
#         leftover_list.append(
#             items
#         )
    
#     leftover_items_dict = {}
#     for items in leftover_list:
#         item_name = items['dish_name'] or items['product__name']

#         if item_name in leftover_items_dict:
#             leftover_items_dict[item_name]['quantity'] += items['quantity']
#             leftover_items_dict[item_name]['price'] += items['price']
#         else:
#             leftover_items_dict[item_name] = item_name
#             leftover_items_dict[item_name]['quantity'] = items['quantity']
#             leftover_items_dict[item_name]['price'] = items['dish_price'] or items['product_price']
    

#     sale_staff_items_list = []
#     sale_staff_items = SaleItem.objects.filter(sale__void = False, sale__staff = True , time = datetime.datetime.today()).values('dish__name', 'dish__price', 'product__name', 'product__price', 'quantity')

#     for items in sale_staff_items:
#         sale_staff_items_list.append(
#             items
#         )
    
#     sale_staff_items_dict = {}
#     for items in sale_staff_items_list:
#         item_name = items['dish_name'] or items['product__name']

#         if item_name in sale_staff_items_dict:
#             sale_staff_items_dict[item_name]['quantity'] += items['quantity']
#             sale_staff_items_dict[item_name]['price'] += items['price']
#         else:
#             sale_staff_items_dict[item_name] = item_name
#             sale_staff_items_dict[item_name]['quantity'] = items['quantity']
#             sale_staff_items_dict[item_name]['price'] = items['dish_price'] or items['product_price']


#     cash_in_hand = total_sales + total_change - total_expenses

#     logger.info(cash_in_hand)
#     logger.info(sale_items_dict)
#     logger.info(leftover_items_dict)
#     logger.info(sale_staff_items_dict)
#     logger.info(total_sales)
#     logger.info(total_leftovers)

#     return render(request, 'admin_cashup_report.html',{
#         'now': datetime.datetime.today(),
#         'sales': sale_items_dict,
#         'leftovers': leftover_items_dict,
#         'staff': sale_staff_items_dict,
#         'total_sales': total_sales,
#         'total_leftovers': total_leftovers,
#         'declared_cash': cashier_cash,
#         'variance': cash_in_hand - cashier_cash,
#         }, 
#         status = 200)

@login_required
def cashier_handover_shift(request):
    if request.method == 'GET':
        try:
            handover_records = []
            logger.info(handover_records)
            return JsonResponse({'success': True, 'records':handover_records}, status=200)
        except Exception as e:
            logger.info(e)
            return JsonResponse({'success': False}, status=400)
    elif request.method == 'POST':
        try:
            cash_in_hand = 0
            cashier_id = request.user.id

            data = json.loads(request.body)
            float_cash = data.get('float')

            cashier_data = User.objects.get(id = cashier_id)
            sales = Sale.objects.filter(cashier__id=cashier_id, date=datetime.datetime.today(), void=False).values('total_amount')
            change = Change.objects.filter(cashier__id=cashier_id, cashier_give__id=cashier_id, timestamp__date=datetime.datetime.today(), collected=False).values('amount')
            expenses = CashierExpense.objects.filter(cashier__id=cashier_id, date=datetime.datetime.today()).values('amount')
            

            total_sales = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
            total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
            total_change = change.aggregate(Sum('amount'))['amount__sum'] or 0
            
            cash_in_hand = total_sales + total_change - total_expenses
            logger.info(f'cash in hand: {cash_in_hand}')

            # CashierHandover.objects.create(
            #     cashier_checking_out = cashier_data,
            #     total_sales = total_sales,
            #     total_expenses = total_expenses,
            #     cash_in_hand = cash_in_hand,
            #     cash_float = float_cash
            # )
            return JsonResponse({'success': True}, status=200)
        except Exception as e:
            logger.info(e)
            return JsonResponse({'success': False, 'message':f'{e}'}, status=400)
    return JsonResponse({'success': False , 'message': 'Invalid request'}, status=500)
    


def offline_view(request):
    return render(request, 'offline.html')

@login_required
def sync_sales(request):
    if request.method == 'POST':
        try:
            pending_sales = json.loads(request.body)
            for sale_data in pending_sales:
                _process_sale_data(sale_data, request.user)
            return JsonResponse({'success': True}, status=200)
        except Exception as e:
            logger.error(f'Error syncing sales: {str(e)}')
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)
