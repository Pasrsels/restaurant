import json
import csv
import io
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.views import View
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.utils.timezone import localdate
from reportlab.lib.pagesizes import A4, letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Line
from .models import Production, ProductionItems, Ingredient, CheckList
from django.db import models
from django.db.models import Q, Sum, F, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.apps import apps
from io import BytesIO
import os

def get_purchase_order_model():
    return apps.get_model('inventory', 'PurchaseOrder')

# Table styling functions
def get_table_style(header_bg_color='#2c3e50', text_color='#2c3e50', font_size=9):
    """Return a consistent table style with the specified colors and font size."""
    return [
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_bg_color)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), font_size + 1),  # Slightly larger header
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Body styling
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), font_size),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor(text_color)),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
    ]

def get_paragraph_style(style_name, **kwargs):
    """Return a consistent paragraph style with the specified overrides."""
    defaults = {
        'fontName': 'Helvetica',
        'fontSize': 9,
        'textColor': colors.HexColor('#2c3e50'),
        'leading': 12,
        'spaceAfter': 6,
        'spaceBefore': 6
    }
    defaults.update(kwargs)
    return ParagraphStyle(style_name, **defaults)

# Import models explicitly to avoid circular imports
from .models import (
    Dish, 
    Ingredient,
    Production,
    ProductionItems,
    ProductionRawMaterials,
    AllocatedRawMaterials,
    OverrideHistory,
    Transfer,
    Product
)

# Configure logging
logger = logging.getLogger(__name__)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from utils.email import EmailThread
from django.core.mail import EmailMessage
from finance.models import COGS
from datetime import timedelta, time
import datetime
from .tasks import inventory_task
from django.db.models import Q
from finance.models import (
    Sale,
    SaleItem,
    Sale,
    SaleItem,
    CashBook,
    Expense, 
    CashUp,
    ExpenseCategory
)
from .tasks import (
    send_production_creation_notification,
    transfer_notification,
    supplier_email,
    sendProductHistory,
    autoConfirmProdPlan
)
from . forms import (
    MealForm,
    AddProductForm,
    AddSupplierForm,
    CreateOrderForm,
    noteStatusForm,
    PurchaseOrderStatus,
    UnitOfMeasurementForm,
    EditProductForm,
    ProductionPlanInlineForm,
    DishForm, 
    IngredientForm,
    TransferForm,
    CreateBudgetItemForm,
    CreateStockTakeForm
)

from utils.supplier_best_price import best_price
from utils.utils import render_to_pdf
from permisions.permisions import admin_required, chef_only_required, stores_person_only_required, chef_or_stores_view_required

def is_ajax(request):
    """Check if the request is an AJAX request"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

@login_required
def unit_of_measurement(request):
    if request.method == 'GET':
        units = UnitOfMeasurement.objects.all().values()
        return JsonResponse(list(units), safe=False)
    
    if request.method == 'POST':
        """
            name
        """
        try:
            data = json.loads(request.body)
            unit_name = data.get('name')
        except Exception as e:
            return JsonResponse({'success':False, 'message':'Invalid Json data'}, status=400)
        
        if unit_name:
            unit_name = unit_name.lower()
            
            #validation for existance
            if UnitOfMeasurement.objects.filter(unit_name=unit_name).exists():
                return JsonResponse({'success':False, 'message':f'Unit of Measurement with the name {unit_name} exists'}, status=400)
            
            unit_obj = UnitOfMeasurement(
                unit_name=unit_name
            )
            unit_obj.save()
            logger.info(f'{unit_obj.unit_name}, successfully created')
            return JsonResponse({'success':True}, status=200)
        
        return JsonResponse({'success':False, 'message':'Unit of measurement is invalid'}, status=400)
    
    return JsonResponse({'success':False, 'message':'Invalid request'}, status=400)

@login_required
def generate_report(request, eod_id):
    """
        cashier, servers and production variance
    """
    end_of_day = EndOfDay.objects.filter(id=eod_id, branch=request.user.branch).first()
    cashier_end_of_days = EndOfDayCashier.objects.filter(end_of_day=end_of_day)
    production = Production.objects.filter(date_created=end_of_day.date)
    
    logger.info(cashier_end_of_days)

    cashier_list = []
    total_sales = 0
    total_cashed_amount = 0
    total_variance = 0
    
    for c in cashier_end_of_days:
        cashier_obj = c.cashier
        sales = getattr(c, 'sales', 0) if hasattr(c, 'sales') else 0
        cashed_amount = c.cashed_amount or 0
        variance = getattr(c, 'variance', 0) if hasattr(c, 'variance') else 0
        cashier_list.append({
            'cashier': cashier_obj,
            'sales': sales,
            'cashed_amount': cashed_amount,
            'variance': variance,
            'object': c,
        })
        total_sales += sales
        total_cashed_amount += cashed_amount
        total_variance += variance

    servers_variance_total = end_of_day.variance

    production_variance_total = 0
    for prod in production:
        production_variance_total += prod.productionitems_set.aggregate(total=Sum('wastage'))['total'] or 0

    context = {
        'cashier_list': cashier_list,
        'cashier_totals': {
            'total_sales': total_sales,
            'total_cashed_amount': total_cashed_amount,
            'total_variance': total_variance,
        },
        'servers_variance_total': servers_variance_total,
        'production_variance_total': production_variance_total,
    }

    return render_to_pdf('end_of_day_totals.html', context)

@login_required
def products(request):
    raw_materials = Product.objects.filter(branch=request.user.branch)
    return render(request, 'inventory/products.html', 
        {
            'raw_materials':raw_materials,
            'count':raw_materials.count()
        }
    )


def finishedProduct(cashier_id):
    PurchaseOrder = get_purchase_order_model()
    product_info = Product.objects.filter(finished_product=True)

    today = datetime.datetime.today()
    start_of_day = datetime.datetime.combine(today, time.min)
    end_of_day = datetime.datetime.combine(today, time.max)

    p_order_received = PurchaseOrder.objects.filter(
        order_date__range=(start_of_day, end_of_day)
    ).filter(
        Q(received=True) | Q(is_partial=True)
    )

    logger.info(f"Received Orders: {p_order_received}")
    logger.info(f"Products: {product_info}")

    product_list = []
    previous_day = datetime.date.today() - datetime.timedelta(days=1)

    for product in product_info:

        # Get starting stock from yesterday
        try:
            stock_entry = EndOfDayStock.objects.get(date=previous_day, product=product)
            starting_stock = stock_entry.quantity  # assuming field name is 'quantity'
        except EndOfDayStock.DoesNotExist:
            starting_stock = 0

        # Handle received stock
        for order in p_order_received:
            received_items = PurchaseOrderItem.objects.filter(
                purchase_order_id=order.id,
                product=product
            )
            for item in received_items:
                existing_entry = next(
                    (entry for entry in product_list if entry['Product_Name'] == product.name), None
                )
                if existing_entry:
                    existing_entry['Stock'] += item.received_quantity
                else:
                    product_list.append({
                        'Product_Name': product.name,
                        'Stock': item.received_quantity,
                        'Start': starting_stock,
                        'Current': product.quantity,
                        'Sold': 0
                    })
                logger.info({'received_entry': product_list})

        # Handle sales
        product_sales = SaleItem.objects.filter(
            sale__date=datetime.date.today(),
            product=product,
            sale__cashier__id = cashier_id
        )
        for sale in product_sales:
            existing_entry = next(
                (entry for entry in product_list if entry['Product_Name'] == product.name), None
            )
            if existing_entry:
                existing_entry['Sold'] += sale.quantity
            else:
                product_list.append({
                    'Product_Name': product.name,
                    'Stock': 0,
                    'Start': starting_stock,
                    'Current': product.quantity,
                    'Sold': sale.quantity
                })

    #Wrong logic here will look to see how i was thinking here
    #Calculate current stock
    # for entry in product_list:
    #     entry['Current'] = entry['Start'] + entry['Stock'] - entry['Sold']

    logger.info({'final_stock_data': product_list})

    #Celery task
    sendProductHistory.delay(product_list)

    return product_list

@login_required
def productHistory(request):
    if request.method == 'GET':
        product_info = Product.objects.filter(finished_product=True, branch=request.user.branch)

        today = datetime.datetime.today()
        start_of_day = datetime.datetime.combine(today, time.min)
        end_of_day = datetime.datetime.combine(today, time.max)

        p_order_received = PurchaseOrder.objects.filter(
            order_date__range=(start_of_day, end_of_day), branch=request.user.branch
        ).filter(
            Q(received=True) | Q(is_partial=True)
        )

        logger.info(f"Received Orders: {p_order_received}")
        logger.info(f"Products: {product_info}")

        product_list = []
        previous_day = datetime.date.today() - datetime.timedelta(days=1)

        for product in product_info:

            # Get starting stock from yesterday
            try:
                stock_entry = EndOfDayStock.objects.get(date=previous_day, product=product, branch=request.user.branch)
                starting_stock = stock_entry.quantity  # assuming field name is 'quantity'
            except EndOfDayStock.DoesNotExist:
                starting_stock = 0

            # Handle received stock
            for order in p_order_received:
                received_items = PurchaseOrderItem.objects.filter(
                    purchase_order_id=order.id,
                    product=product,
                    branch=request.user.branch
                )
                for item in received_items:
                    existing_entry = next(
                        (entry for entry in product_list if entry['Product_Name'] == product.name), None
                    )
                    if existing_entry:
                        existing_entry['Stock'] += item.received_quantity
                    else:
                        product_list.append({
                            'Product_Name': product.name,
                            'Stock': item.received_quantity,
                            'Start': starting_stock,
                            'Current': 0,
                            'Sold': 0
                        })
                    logger.info({'received_entry': product_list})

            # Handle sales
            product_sales = SaleItem.objects.filter(
                sale__date=datetime.date.today(),
                product=product,
                sale__branch=request.user.branch
            )
            for sale in product_sales:
                existing_entry = next(
                    (entry for entry in product_list if entry['Product_Name'] == product.name), None
                )
                if existing_entry:
                    existing_entry['Sold'] += sale.quantity
                else:
                    product_list.append({
                        'Product_Name': product.name,
                        'Stock': 0,
                        'Start': starting_stock,
                        'Current': 0,
                        'Sold': sale.quantity
                    })

        #Calculate current stock
        for entry in product_list:
            entry['Current'] = entry['Start'] + entry['Stock'] - entry['Sold']

        logger.info({'final_stock_data': product_list})

        #Celery task
        sendProductHistory.delay(product_list)

        return JsonResponse({'success': True, 'data': product_list}, status=200)
    elif request.method == "POST":
        product_data = Product.objects.filter(finished_product = True, branch=request.user.branch)
        end_of_day_stock = None
        for product in product_data:
            try:
                end_of_day_stock = EndOfDayStock.objects.get(product = product, date = datetime.datetime.today(), branch=request.user.branch)
            except Exception as e:
                logger.info(e)
            if end_of_day_stock:
                logger.info(f'Product: {product.name} end of day already logged')
                logger.info(end_of_day_stock.quantity)
            else:
                log = EndOfDayStock.objects.create(
                    product = product,
                    quantity = product.quantity,
                    branch=request.user.branch
                )
                logger.info(log)
        return JsonResponse({'success': True}, status = 200)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status = 505)

@admin_required
@login_required
def inventory(request):
    product_name = request.GET.get('name', '')
    if product_name:
        
        return JsonResponse(list(Product.objects.filter(name=product_name, branch=request.user.branch).values(
                'unit__unit_name',
                'name',
                'id'
            )), safe=False)
    return JsonResponse({'error':'product doesnt exists'})


@login_required
def add_product_category(request):
    categories = Category.objects.all().values()
    
    if request.method == 'POST':
        data = json.loads(request.body)
        category_name = data['name']
        
        if Category.objects.filter(name=category_name).exists():
            return JsonResponse({'error', 'Category Exists'})
        
        Category.objects.create(
            name=category_name
        )
    return JsonResponse(list(categories), safe=False)   


@login_required
def product(request):

    if request.method == 'POST':
        # payload
        """
            name,
            price: float,
            cost: float,
            unit of measurement: int,
            quantity: int,
            category,
            tax_type,
            min_stock_level,
            portion_multiplier: int
            description
            raw_material:bool,
            finished_product:bool,
            packaging:bool
        """
        try:
            data = json.loads(request.body)
        except Exception as e:
            return JsonResponse({'success':False, 'message':'Invalid data'})
        
        
        # validation for existance
        if Product.objects.filter(name=data['name'], branch=request.user.branch).exists():
            return JsonResponse({'success':False, 'message':f'Product exists'})

        try:
            category = Category.objects.get(id=data['category'])
        except Category.DoesNotExist:
            return JsonResponse({'success':False, 'message':f'Category doesn\'t Exists'})
        
        try: 
            unit = UnitOfMeasurement.objects.get(id=int(data['unit']))
        except Exception as e:
            return JsonResponse({'success':False, 'message':f'Unit of Measurement Doesnt Exists'})
        
        product = Product.objects.create(
            name = data['name'],
            price = data['price'],
            cost = data['cost'],
            quantity = data['quantity'],
            category = category,
            tax_type = data['tax_type'],
            min_stock_level = data['min_stock_level'],
            description = data['description'], 
            raw_material = True if data['raw_material'] else False,
            finished_product = True if data['finished_product'] else False,
            unit = unit,
            branch = request.user.branch,
            packaging= True if data['packaging'] else False,
        )
        product.save()
        logger.info(f'product saved')
        return JsonResponse({'success':True})
            
    if request.method == 'GET':
        products = Product.objects.filter(branch=request.user.branch).values(
            'id',
            'name',
        )
        return JsonResponse(list(products), safe=False)
    
    return JsonResponse({'success':False, 'message':'Invalid request'})


@login_required
def product_detail(request, product_id):
    if request.method == 'GET':
        print('here')
        try:
            product = Product.objects.get(id=product_id, branch=request.user.branch)
        except Product.DoesNotExist:
            return JsonResponse({
                'error': f'Product with ID {product_id} does not exist'
            }, status=404)

        logs = Logs.objects.filter(product=product, branch=request.user.branch).order_by('-timestamp')[:5]

        logs_data = [
            {
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M'),
                'action': log.action,
                'user': log.user.username if log.user else 'System',
                'quantity': log.quantity,
                'total_quantity': log.total_quantity,
                'description': log.description if log.description else ''
            }
            for log in logs
        ]

        data = {
            'id': product.id,
            'name': product.name,
            'cost': float(product.cost),
            'quantity': float(product.quantity),
            'unit': product.unit.unit_name,
            'logs': logs_data
        }

        return JsonResponse(data, safe=False)
    
    elif request.method == 'DELETE':
        try:
            logger.info(product_id)
            product = Product.objects.get(id = product_id, branch=request.user.branch)
            product.delete()

            return JsonResponse({"success": True}, status=200)
        except Exception as e:
            return JsonResponse({'success': False, 'message': e}, status=405)



@login_required
def production_rm_detail(request, rm_id):
    try: 
        product = ProductionRawMaterials.objects.get(id=rm_id)
        logger.info(product)
    except Product.DoesNotExist:
        messages.warning(request, f'Product with ID: {rm_id} doesn\'t exists')
        
    logs = ProductionLogs.objects.filter(product=product, branch=request.user.branch)

    return render(request, 'inventory/production_rm_detail.html', 
        {
            'product': product,
            'logs': logs,
        }
    )
    
    
@login_required
def edit_inventory(request, product_id):
    
    try: 
        product = Product.objects.get(id=product_id, branch=request.user.branch)
    except Product.DoesNotExist:
        messages.warning(request, f'Product with ID: {product_id} doesn\'t exists')
        
    form = EditProductForm(instance=product)
    logger.info(request.FILES)
    if request.method == 'POST':
        form = EditProductForm(request.POST, request.FILES, instance=product)
        
        if form.is_valid():
            form.save()
            
        Logs.objects.create(
            user=request.user, 
            action= 'Stock update',
            product=product,
            quantity=request.POST['quantity'],
            total_quantity=product.quantity,
            branch=request.user.branch
        )
        
        messages.success(request, f'{product.name} update succesfully')
        return redirect('inventory:products')
    
    return render(request, 'inventory/edit_product.html', 
            {
                'form':form,
                'product':product
            }
        )
    

@login_required
def suppliers(request):
    form = AddSupplierForm()
    suppliers = Supplier.objects.filter(branch=request.user.branch)
    return render(request, 'inventory/suppliers.html', 
        {
            'suppliers':suppliers,
            'form':form
        }
    )
    

@login_required
def supplier_list_json(request):
    suppliers = Supplier.objects.filter(branch=request.user.branch).values(
        'id',
        'name'
    )
    return JsonResponse(list(suppliers), safe=False)


@login_required
def create_supplier(request):
    #payload
    """
        name 
        contact
        email
        phone 
        address
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        
        name = data['name']
        contact = data['contact']
        email = data['email']
        phone = data['phone']
        address = data['address']
        
        if not name or not contact or not email or not phone or not address:
            return JsonResponse({'success': False, 'message':'Fill in all the form data'}, status=400)
        
        if Supplier.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'message':f'Supplier{name} already exists'}, status=400)
        
        supplier = Supplier(
            name = name,
            contact_name = contact,
            email = email,
            phone = phone,
            address = address,
            branch=request.user.branch
        )
        supplier.save()
        logger.info(f'Supplier successfully created {supplier.name}')
        return JsonResponse({'success': True}, status=200)
    
        
@login_required
def edit_supplier(request, supplier_id):
    # payload
    """
        supplier_id
    """
    
    if request.method == 'POST':
        data = json.loads(request.post)
        supplier_id = data['supplier_id']
        
        if supplier_id:
            try:
                supplier = Supplier.objects.get(id=supplier_id, branch=request.user.branch)
            except Exception as e:
                return JsonResponse({'success': False, 'message':f'{supplier_id} doesn\'t exists'}, status=400)
                
        form = AddSupplierForm(request.post, instance=supplier)
        
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True}, status=400)
    return JsonResponse({'success': True})


@login_required
def purchase_orders(request):
    form = CreateOrderForm()
    status_form = PurchaseOrderStatus()
    orders = PurchaseOrder.objects.filter(branch=request.user.branch).order_by('-order_date')
    return render(request, 'inventory/purchase_orders.html', 
        {
            'form':form,
            'orders':orders,
            'status_form':status_form 
        }
    )
      
@login_required
def create_purchase_order(request):
    
    # include the vat account and the purchase order account and the cash account
    
    if request.method == 'GET':
        supplier_form = AddSupplierForm()
        product_form = AddProductForm()
        suppliers = Supplier.objects.filter(branch=request.user.branch)
        note_form = noteStatusForm()
        unit_form = UnitOfMeasurementForm()
        
        return render(request, 'inventory/create_purchase_order.html',
            {
                'product_form':product_form,
                'supplier_form':supplier_form,
                'suppliers':suppliers,
                'note_form':note_form,
                'unit_form':unit_form
            }
        )

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            purchase_order_data = data.get('purchase_order', {})
            purchase_order_items_data = data.get('po_items', [])
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload'}, status=400)

        supplier_id = purchase_order_data['supplier']
        delivery_date = purchase_order_data['delivery_date']
        status = purchase_order_data['status']
        notes = purchase_order_data['notes']
        total_cost = Decimal(purchase_order_data['total_cost'])
        discount = Decimal(purchase_order_data['discount'])
        handling_amount = Decimal(purchase_order_data['handling_amount'])
        tax_amount = Decimal(purchase_order_data['tax_amount'])
        other_amount = Decimal(purchase_order_data['other_amount'])
    
        if not all([supplier_id, delivery_date, status, total_cost, tax_amount]):
            return JsonResponse({'success': False, 'message': 'Missing required fields'}, status=400)

        try:
            supplier = Supplier.objects.get(id=supplier_id, branch=request.user.branch)
        except Supplier.DoesNotExist:
            return JsonResponse({'success': False, 'message': f'Supplier with ID {supplier_id} not found'}, status=404)

        try:
            with transaction.atomic():
                purchase_order = PurchaseOrder(
                    order_number=PurchaseOrder.generate_order_number(),
                    supplier=supplier,
                    delivery_date=delivery_date,
                    status=status,
                    notes=notes,
                    total_cost=total_cost,
                    discount=discount,
                    tax_amount=tax_amount,
                    handling_amount=handling_amount,
                    other_amount=other_amount,
                    is_partial = False,
                    received = False,
                    branch=request.user.branch
                )
                purchase_order.save()

                for item_data in purchase_order_items_data:
                    product_name = (item_data['product'])
                    quantity = float(item_data['quantity'])
                    unit_cost = Decimal(item_data['price'])
                    note = item_data['note']
                    note = item_data['note']

                    if not all([product_name, quantity, unit_cost]):
                        transaction.set_rollback(True)
                        return JsonResponse({'success': False, 'message': 'Missing fields in item data'}, status=400)

                    try:
                        product = Product.objects.get(name=product_name, branch=request.user.branch)
                    except Product.DoesNotExist:
                        transaction.set_rollback(True)
                        return JsonResponse({'success': False, 'message': f'Product with Name {product_name} not found'}, status=404)

                    purchase_order_item = PurchaseOrderItem.objects.create(
                        purchase_order=purchase_order,
                        product=product,
                        quantity=quantity,
                        unit_cost=unit_cost,
                        received_quantity=0,
                        received=False,
                        note=note
                    )

                    supplier_email(purchase_order.supplier.id, purchase_order_item, request.user.branch)

                # consider to put expenses
                if purchase_order.status == 'received': 
                    category, _ = ExpenseCategory.objects.get_or_create(
                        name = 'Inventory'
                    )
                    
                    expense = Expense.objects.create(
                        category = category,
                        amount = purchase_order.total_cost,
                        user = request.user,
                        description = f'Purchase order{purchase_order.order_number}',
                        cancel = False,
                        branch=request.user.branch
                    )
                    
                    CashBook.objects.create(
                        amount = purchase_order.total_cost,
                        expense = expense,
                        credit = True,
                        description = f'Expense purchase order{purchase_order.order_number}',
                        branch=request.user.branch
                    )

        except Exception as e:
            return JsonResponse({'success': False, 'message': f'{str(e)} fefere'}, status=500)

        return JsonResponse({'success': True, 'message': 'Purchase order created successfully'})

    
@login_required
@transaction.atomic
def change_purchase_order_status(request, order_id):
    try:
        purchase_order = PurchaseOrder.objects.get(id=order_id, user__branch=request.user.branch)
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'error': f'Purchase order with ID: {order_id} doesn\'t exist'}, status=404)

    try:
        data = json.loads(request.body)
        status = data['status']
        
        if status:
            purchase_order.status=status
            if purchase_order.status == 'received':
                purchase_order.save()
                
                category, _ = ExpenseCategory.objects.get_or_create(
                    name = 'Inventory'
                )
                
                expense = Expense.objects.create(
                    category = category,
                    amount = purchase_order.total_cost - purchase_order.tax_amount,
                    user = request.user,
                    description = f'Expense purchase order{purchase_order.order_number}',
                    cancel = False,
                    branch=request.user.branch
                )
                
                CashBook.objects.create(
                    amount = purchase_order.total_cost,
                    expense = expense,
                    credit = True,
                    description = f'Expense purchase order{purchase_order.order_number}',
                    branch=request.user.branch
                )
            
            return JsonResponse({'success':True}, status=200)
        else:
            return JsonResponse({'success':False, 'message':'Status is required'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON payload'}, status=400)


@login_required
def print_purchase_order(request, order_id):
    try:
        purchase_order = PurchaseOrder.objects.get(id=order_id, branch=request.user.branch)
    except PurchaseOrder.DoesNotExist:
        messages.warning(request, f'Purchase order with ID: {order_id} doesn\'t exists')
        return redirect('inventory:purchase_orders')
    
    try:
        purchase_order_items = PurchaseOrderItem.objects.filter(purchase_order=purchase_order)
    except PurchaseOrderItem.DoesNotExist:
        messages.warning(request, f'Purchase order with ID: {order_id} doesn\'t exists')
        return redirect('inventory:purchase_orders')
    
    return render(request, 'inventory/print_purchase_order.html', 
        {
            'orders':purchase_order_items,
            'purchase_order':purchase_order
        }
    )
    

@login_required
def purchase_order_detail(request, order_id):
    try:
        purchase_order = PurchaseOrder.objects.get(id=order_id, branch=request.user.branch)
    except PurchaseOrder.DoesNotExist:
        messages.warning(request, f'Purchase order with ID: {order_id} doesn\'t exists')
        return redirect('inventory:purchase_orders')
    
    try:
        purchase_order_items = PurchaseOrderItem.objects.filter(purchase_order=purchase_order)
    except PurchaseOrderItem.DoesNotExist:
        messages.warning(request, f'Purchase order with ID: {order_id} doesn\'t exists')
        return redirect('inventory:purchase_orders')
    
    return render(request, 'inventory/purchase_order_detail.html', 
        {
            'orders':purchase_order_items,
            'purchase_order':purchase_order
        }
    )
    
    
@login_required
def delete_purchase_order(request, purchase_order_id):
    if request.method != "DELETE":
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

    try:
        purchase_order = PurchaseOrder.objects.get(id=purchase_order_id, branch=request.user.branch)
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Purchase order with ID {purchase_order_id} not found'}, status=404)

    try:
        purchase_order.delete()
        return JsonResponse({'success': True, 'message': 'Purchase order deleted successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def receive_order(request, order_id):
    try:
        purchase_order = PurchaseOrder.objects.get(id=order_id, branch=request.user.branch)
        purchase_order_items = PurchaseOrderItem.objects.filter(purchase_order=purchase_order)
    except PurchaseOrder.DoesNotExist:
        messages.warning(request, f'Purchase order with ID: {order_id} doesn\'t exists')
        return redirect('inventory:purchase_orders')
    return render(request, 'inventory/receive_order.html', 
        {
            'orders':purchase_order_items,
            'purchase_order':purchase_order
        }
    )

    
@login_required
@transaction.atomic
def process_received_order(request):
    if request.method == 'POST':
        try:
       
            data = json.loads(request.body)
            order_item_id = data.get('id')
            quantity = int(data.get('quantity', 0))

            if not order_item_id or quantity <= 0:
                return JsonResponse({'success': False, 'message': 'Invalid data'}, status=400)

            order_item = PurchaseOrderItem.objects.select_related('purchase_order', 'product').get(id=order_item_id, purchase_order__branch=request.user.branch)
            
            if (quantity + order_item.received_quantity) > order_item.quantity:
                return JsonResponse({'success': False, 'message': 'Quantity received cannot be more.'})
             
            purchase_order = order_item.purchase_order
            product = order_item.product
            
            average_cost = Decimal(((Decimal(product.cost) * Decimal(product.quantity)) + (Decimal(order_item.unit_cost) * Decimal(quantity)))) / Decimal((quantity + product.quantity))

            product.quantity += quantity
            product.cost = average_cost
            product.save()
            
            inventory_task.delay(product.id)
     
            Logs.objects.create(
                purchase_order=purchase_order,
                user=request.user, 
                action='stock in',
                product=product,
                quantity=quantity,
                description=f'Stock in from {purchase_order.order_number}',
                total_quantity=product.quantity,
                # branch=request.user.branch
            )

            order_item.receive_items(quantity)
            order_item.check_received()
            
            return JsonResponse({'success': True, 'message': 'Inventory updated successfully'}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload'}, status=400)
        except PurchaseOrderItem.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Purchase Order Item not found'}, status=404)
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'An error occurred: {str(e)}'}, status=500)


@login_required   
def production_plans(request):
    from datetime import datetime, timedelta
    
    # Get date filter from request, default to today
    selected_date = request.GET.get('date', datetime.now().strftime('%Y-%m-%d'))
    date_filter = None
    
    try:
        # Convert string to date object
        if selected_date == 'yesterday':
            filter_date = datetime.now().date() - timedelta(days=1)
        elif selected_date == 'today':
            filter_date = datetime.now().date()
        elif selected_date == 'week':
            # Calculate week start (Monday) and end (Sunday)
            today = datetime.now().date()
            week_start = today - timedelta(days=today.weekday())  # Monday
            week_end = week_start + timedelta(days=6)  # Sunday
            filter_date = week_start  # Use week start as filter date
            date_filter = 'week'
        else:
            filter_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except:
        filter_date = datetime.now().date()
    
    # Filter plans by date - date_created is already a DateField
    if date_filter == 'week':
        plans = Production.objects.filter(
            branch=request.user.branch,
            date_created__range=[week_start, week_end]
        ).order_by('date_created')
    else:
        plans = Production.objects.filter(
            branch=request.user.branch,
            date_created=filter_date
        ).order_by('date_created')
    transfer_count = Transfer.objects.filter(status=False, branch=request.user.branch).count()
    products = Product.objects.filter(branch=request.user.branch).order_by('name')[:15]  # Limit to 15 products for sidebar

    # Use different template for chefs and stores person
    if request.user.role in ['chef', 'stores_person']:
        # For stores person, get plans that are confirmed but not declared
        if request.user.role == 'stores_person':
            declaration_plans = Production.objects.filter(
                branch=request.user.branch,
                status=True,  # Confirmed by chef
                declared=False  # Not yet declared by stores person
            ).order_by('date_created')
        else:
            declaration_plans = plans
            
        context = {
            'plans': plans, 
            'declaration_plans': declaration_plans,
            'transfer_count': transfer_count,
            'products': products,
            'selected_date': filter_date,
            'today': datetime.now().date(),
            'yesterday': datetime.now().date() - timedelta(days=1),
            'date_filter': date_filter
        }
        
        # Add week context if week filter is active
        if date_filter == 'week':
            context.update({
                'week_start': week_start,
                'week_end': week_end
            })
        
        return render(request, 'inventory/production_plans_chef.html', context)

    return render(request, 'inventory/production_plans.html', {'plans': plans, 'transfer_count': transfer_count})

@login_required
def production_plans_admin(request):
    from datetime import datetime, timedelta
    
    # Get date filter from request, default to today
    selected_date = request.GET.get('date', datetime.now().strftime('%Y-%m-%d'))
    date_filter = None
    
    try:
        # Convert string to date object
        if selected_date == 'yesterday':
            filter_date = datetime.now().date() - timedelta(days=1)
        elif selected_date == 'today':
            filter_date = datetime.now().date()
        elif selected_date == 'week':
            # Calculate week start (Monday) and end (Sunday)
            today = datetime.now().date()
            week_start = today - timedelta(days=today.weekday())  # Monday
            week_end = week_start + timedelta(days=6)  # Sunday
            filter_date = week_start  # Use week start as filter date
            date_filter = 'week'
        else:
            filter_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except:
        filter_date = datetime.now().date()
    
    # Filter plans by date - date_created is already a DateField
    if date_filter == 'week':
        plans = Production.objects.filter(
            branch=request.user.branch,
            date_created__range=[week_start, week_end]
        ).order_by('date_created')
    else:
        plans = Production.objects.filter(
            branch=request.user.branch,
            date_created=filter_date
        ).order_by('date_created') 
    
    transfer_count = Transfer.objects.filter(status=False, branch=request.user.branch).count()
    
    # Check if it's an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return only the content for the dynamic container
        return render(request, 'inventory/production_plans_content.html', {
            'plans': plans,
            'transfer_count': transfer_count,
            'selected_date': selected_date,
            'filter_date': filter_date,
            'date_filter': date_filter
        })
    else:
        # Return full page for regular requests
        return render(request, 'inventory/production_plans.html', {
            'plans': plans, 
            'transfer_count': transfer_count,
            'selected_date': selected_date,
            'filter_date': filter_date,
            'date_filter': date_filter
        })

@login_required
@transaction.atomic
def create_production_plan(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(data)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)

        items = data.get('cart', [])
        if not items or not isinstance(items, list):
            return JsonResponse({'success': False, 'message': 'Invalid data: items should be a list'}, status=400)
        
        production_plan = None
        auto_confirm = data.get('auto', '')

        if Production.objects.filter(declared=False, branch=request.user.branch).exists():
            pass
            # return JsonResponse({'success': False, 'message': 'Please declare all the production plans you have.'}, status=400)

        production_plan = None

        if auto_confirm:
            if data.get('id'):
                production_plan = Production.objects.get(id = data.get('id'), branch=request.user.branch)
            else:
                production_latest = Production.objects.filter(date_created = datetime.date.today(), branch=request.user.branch).order_by('-time_created').first()
                if production_latest:
                    production_plan = production_latest
                else:
                    return JsonResponse({'success': False, 'message': 'No production Plan for Today.'}, status=400)
        else:
            # Create a new production plan
            production_plan = Production.objects.create(status=False, declared=False, branch=request.user.branch)

        logger.info(f"production_plan: {production_plan.branch}")

        dish_names = [item.get('dish') for item in items if item.get('dish')]
        dishes = Dish.objects.filter(name__in=dish_names, branch = request.user.branch)
        dish_map = {dish.name: dish for dish in dishes}

        if len(dish_map) != len(dish_names):
            return JsonResponse({'success': False, 'message': 'Some dishes do not exist'}, status=404)

        production_items = []
        production_items_update = []
        raw_materials_to_checklist = set()

        for item in items:
            portions = item.get('portions')
            dish_name = item.get('dish')
            total_cost = item.get('total_cost')

            if not portions or not dish_name:
                return JsonResponse({'success': False, 'message': 'Missing data: portions or dish'}, status=400)

            dish = dish_map.get(dish_name)

            if dish is None:
                return JsonResponse({'success': False, 'message': f'Dish {dish_name} does not exist'}, status=404)


            ingredients = Ingredient.objects.filter(dish=dish, minor_raw_material__branch = request.user.branch).select_related('minor_raw_material')
            if auto_confirm:
                existing_items = ProductionItems.objects.filter(production=production_plan)
                for existing_item in existing_items:
                    if existing_item.dish.name == dish_name:
                        production_items_update.append(ProductionItems(
                            id=existing_item.id,
                            production=production_plan,
                            portions=existing_item.portions + portions,
                            dish=dish,
                            total_cost=existing_item.total_cost + total_cost,
                            allocated=False
                        ))
                        break
                else:
                    # Not found, create new
                    production_items.append(ProductionItems(
                        production=production_plan,
                        portions=portions,
                        dish=dish,
                        total_cost=total_cost,
                        allocated=False
                    ))
            else:
                production_items.append(ProductionItems(
                    production=production_plan,
                    portions=portions,
                    dish=dish,
                    total_cost=total_cost,
                    allocated=False
                ))

            # Collect raw materials for checklist creation
            for ingredient in ingredients:
                raw_materials_to_checklist.add(ingredient.minor_raw_material)

        # Bulk create production items to reduce the number of queries
        if production_items:
            ProductionItems.objects.bulk_create(production_items)

        if production_items_update:
            ProductionItems.objects.bulk_update(production_items_update, ['portions', 'total_cost', 'allocated'])

        today = datetime.datetime.today()
        existing_checklists = set(CheckList.objects.filter(date=today, product__in=raw_materials_to_checklist, product__branch=request.user.branch)
                                  .values_list('product_id', flat=True))

        new_checklists = [
            CheckList(product=raw_material, status=False)
            for raw_material in raw_materials_to_checklist
            if raw_material.id not in existing_checklists
        ]
        CheckList.objects.bulk_create(new_checklists)

        send_production_creation_notification(production_plan.id)
        logger.info(data)
        
        auto_confirm = data.get('auto', '')
        if auto_confirm:
            autoConfirmProdPlan(production_plan.id)
            
        #create e_o_d
        e_o_d, created = EndOfDay.objects.get_or_create(date=today, branch=request.user.branch, done=False)
        
        if created:
            
            logger.info(f'End of day created: {e_o_d}')
            
            for dish in production_items:
                EndOfDayItems.objects.create(
                    end_of_day=e_o_d,
                    dish_name=dish.dish.name,
                    total_portions=dish.portions,
                    total_sold=0,
                    staff_portions=0
                )
        else:
            existing_items = EndOfDayItems.objects.filter(end_of_day=e_o_d).values_list('dish_name', flat=True)
            
            logger.info(f'Existing End of day')
            
            for dish in production_items:
                if dish.dish.name not in existing_items:
                    EndOfDayItems.objects.create(
                    end_of_day=e_o_d,
                    dish_name=dish.dish.name,
                    total_portions=dish.portions,
                    total_sold=0,
                    staff_portions=0
                )
                    
                logger.success(f'Added new dish to End of Day: {dish.dish.name}')

        return JsonResponse(
            {
                'success': True, 
                'message': 'Production plan created successfully', 
                'p_plan_id': production_plan.id
            }, 
            status=201
        )

    elif request.method == 'GET':
        form = ProductionPlanInlineForm()
        return render(request, 'inventory/create_production_plan.html', {'form': form})

    return JsonResponse({'success': False, 'message': 'Invalid HTTP method'}, status=405)


@login_required
def dish_json_detail(request):
    try:
        ingredients = []
        
        data = json.loads(request.body)
        dish_id = data.get("dish_id")
        
        logger.info(f"Received dish_id: {dish_id}, type: {type(dish_id)}")
        
        # Validate dish_id
        if not dish_id or dish_id == '':
            return JsonResponse({'success': False, 'message': 'Dish ID is required and cannot be empty'}, status=400)
        
        try:
            dish_id = int(dish_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': f'Invalid dish ID: {dish_id}. Must be a valid number.'}, status=400)
        
        dish = Dish.objects.get(id=dish_id, branch=request.user.branch)
        logger.info(f"Found dish: {dish}")
        
        for ingredient in Ingredient.objects.filter(dish=dish, minor_raw_material__branch=request.user.branch):
            if dish == ingredient.dish:
                ingredients.append(
                {
                    'name' : f'{ingredient.minor_raw_material}',
                    'quantity':ingredient.quantity,
                    'cost': ingredient.minor_raw_material.cost
                }
            )
        
        return JsonResponse({
            'success': True,
            'data': ingredients,
            'portion_multiplier': dish.portion_multiplier
        })
        
    except Dish.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Dish with ID {dish_id} not found in your branch'}, status=400)
    except Exception as e:
        logger.error(f"Error in dish_json_detail: {e}")
        return JsonResponse({'success': False, 'message': f'{e}'}, status=400)


@login_required
def yeseterdays_left_overs(request):
    # payload
    """
    {
        raw_material:id, 
        dish:id
    }
    """
    
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)
        
        raw_material_id = data.get('raw_material')
        dish_id = data.get('dish')
        
        if not raw_material_id:
            return JsonResponse({'success': False, 'message': 'Missing data: raw material'}, status=400)
        
        if not dish_id:
            return JsonResponse({'success': False, 'message': 'Missing data: Dish'}, status=400)
        
        try:
            raw_material = Product.objects.get(id=raw_material_id)
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': f'Raw Material with ID: {raw_material_id} doesn\t exist'}, status=404)
        
        try:
            dish = Dish.objects.get(id=dish_id, major_raw_material=raw_material)
            dish = Dish.objects.get(id=dish_id, major_raw_material=raw_material)
        except Dish.DoesNotExist:
            return JsonResponse({'success': False, 'message': f'Dish with ID: {dish_id} doesn\'t exist'}, status=404)
        
        try:
            latest_plan = Production.objects.latest('time_created')
            try:
                latest_production_item = ProductionItems.objects.get(production=latest_plan, raw_material=raw_material, dish=dish)
                logger.info(f'product: {latest_production_item}')
                latest_raw_material_quantity = latest_production_item.remaining_raw_material or 0
                
                latest_left_over_portion_quantity = (latest_production_item.left_overs * latest_production_item.quantity) / \
                                                    (latest_production_item.quantity  * dish.portion_multiplier) or 0
            except ProductionItems.DoesNotExist:
                logger.warning("No Production Items found for the latest plan.")
                latest_raw_material_quantity = 0
                latest_left_over_portion_quantity = 0

        except Production.DoesNotExist:
            logger.warning("No Production Plans found.")
            latest_raw_material_quantity = 0
            latest_left_over_portion_quantity = 0

       
        return JsonResponse(
            {
                'success':True, 
                'data':{
                    'raw_material_dif':float(latest_raw_material_quantity),
                    'left_over_portion_diff':float(latest_left_over_portion_quantity),
                    'unit_cost':float(raw_material.cost),
                    'unit_of_measurement': raw_material.unit.unit_name
                }
            }
        )
           
    return JsonResponse({'success': False, 'message': 'Invalid HTTP method'}, status=405)


@login_required
def minor_raw_materials(request, pp_id):
    production = Production.objects.get(id=pp_id, branch=request.user.branch)
    return render(request, 'inventory/process_minor_raw_materials.html', {'production':production})

@login_required
def process_raw_materials(request, pp_id):
    production_plan_items = ProductionItems.objects.filter(production__id=pp_id, production__branch=request.user.branch)
    minor_raw_materials = {}
    
    for item in production_plan_items:
        
        for ingredient in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch):
            
            if ingredient.raw_material.name in minor_raw_materials:
                
                minor_raw_materials[ingredient.raw_material.name]['quantity'] += ingredient.quantity

            else:
                minor_raw_materials[ingredient.minor_raw_material.name]={
                    'quantity':ingredient.quantity,
                    'cost':ingredient.minor_raw_material.cost,
                    'production_quantity': item.actual_quantity - item.remaining_raw_material
                }
    return JsonResponse(minor_raw_materials)


@login_required
def confirm_minor_raw_materials(request, pp_id):
    # payload
    """
        [
            "items"{
                'name':{
                    quantity:flaot
                    cost_per_unit:float
                    production_quantity:float
                }
            }
        ]
    """
    try:
        data = json.loads(request.body)
        data =data.get('items')
        raw_material_id = data.get('raw_material_id')
        
    except Exception as e:
        return JsonResponse({'success':False, 'message':f'{e}'}, status=400)
    try:
        production_plan = Production.objects.get(id=pp_id, branch=request.user.branch)
        # production_item = ProductionItem.objects.get(production=production_plan, )
        AllocatedRawMaterials.objects.create(
            production = production_plan,
            raw_material = get_object_or_404(Product, id=raw_material_id )
        )
                
        return JsonResponse({'success':True, 'message':f'Production Plan: {production_plan.production_plan_number} Minor Raw Material Successfully Processed .'}, status=200)
    except Exception as e:
        return JsonResponse({'success':False, 'message':f'{e}'}, status=400)


@login_required
def production_plan_detail(request, pp_id):
    
    if request.method == 'GET':
        try:
            production_plan = Production.objects.get(id=pp_id, branch=request.user.branch)
            production_plan_items = ProductionItems.objects.filter(production=production_plan) 
            dish_ingredients = Ingredient.objects.filter(minor_raw_material__branch=request.user.branch) 
            production_plan_minor_items = MinorProductionItems.objects.filter(production=production_plan)
            p_rm_variance = ProductionVariance.objects.filter(production=production_plan, branch=request.user.branch)

            total_cost_items = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
            total_cost_minor_items = production_plan_minor_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0

            allocated = AllocatedRawMaterials.objects.filter(production=production_plan)

            allocated_rm = []
            raw_materials = []
            
            for item in production_plan_items:
                for ing in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch = request.user.branch):
                    # Fetch or create ProductionRawMaterials instance
                    p_r_m_bf, created = ProductionRawMaterials.objects.get_or_create(
                        product=ing.minor_raw_material,
                        defaults={'quantity': 0}
                    )

                    required_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier)

                    production_inventory = ProductionRawMaterials.objects.filter(product=ing.minor_raw_material, product__branch=request.user.branch).first()
                    current_quantity = production_inventory.quantity if production_inventory else 0

                    expected_quantity = required_quantity - current_quantity

                    raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)
                    
                    if raw_material_found:
                     
                        raw_material_found['quantity'] += required_quantity
                        raw_material_found['expected_quantity'] += expected_quantity
                        raw_material_found['quantity_b_f'] += current_quantity
                    else:
                        raw_materials.append(
                            {
                                'id': ing.minor_raw_material.id,
                                'name': ing.minor_raw_material.name,
                                'quantity_b_f': float(current_quantity),
                                'quantity': float(required_quantity),
                                'expected_quantity': float(expected_quantity),
                            }
                        )
                    """"
                    existing_ids = {rm['id'] for rm in allocated_rm if rm}
                    logger.info([item for item in allocated_rm])
                    if ing.minor_raw_material.id not in existing_ids:
                        allocated_rm.append({
                            'id': ing.minor_raw_material.id,
                            'quantity': (item.portions / item.dish.portion_multiplier),
                            'used': [i.quantity/item.dish.portion_multiplier for i in allocated if i.raw_material.id == ing.minor_raw_material.id],
                        })
                    """


        except Exception as e:
            messages.warning(request, f'Production Plan With ID: {pp_id}, doesn\t exists. Error is {e}')

        return render(request, 'inventory/production_plan_detail.html', 
            {
                'production_plan':production_plan,
                'production_plan_items':production_plan_items,
                'production_plan_minor_items':raw_materials,
                'total_cost_items': total_cost_items,
                'total_cost_minor_items': total_cost_minor_items,
                'allocated_rm':allocated,
                'allocated_rm_per_unit': allocated_rm,
                'confirm': False,
                'dish_ing': dish_ingredients,
                'p_rm_variance': p_rm_variance,
            }
        )
 

@login_required
def confirm_production_plan(request, pp_id):
    if request.method == 'GET':
        try:
            production_plan = Production.objects.get(id=pp_id, branch=request.user.branch)
            production_plan_items = ProductionItems.objects.filter(production=production_plan)
            dish_ingridients = Ingredient.objects.filter(minor_raw_material__branch=request.user.branch)
            total_cost_items = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
            total_overrides = 0
            raw_materials = []
            
            for item in production_plan_items:
                logger.info(item.dish.name)
                for ing in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch):
                   
                    p_r_m_bf, created = ProductionRawMaterials.objects.get_or_create(
                        product=ing.minor_raw_material,
                        defaults={'quantity': 0}
                    )
                    overrided_raw_materials = OverrideHistory.objects.filter(raw_material_overrided = ing.minor_raw_material, raw_material_overrided__branch=request.user.branch)
                    
                    total_overrides_up = sum(item.up if item.up else 0 for item in overrided_raw_materials)
                    total_overrides_down = sum(item.down if item.down else 0 for item in overrided_raw_materials)

                    logger.info(total_overrides_down)
                    logger.info(total_overrides_up)

                    required_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier)
                    logger.info(ing.minor_raw_material.name)

                    production_inventory = ProductionRawMaterials.objects.filter(product=ing.minor_raw_material, product__branch=request.user.branch).first()
                    current_quantity = production_inventory.quantity if production_inventory else 0
                
                    expected_quantity = required_quantity - current_quantity

                    raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)
                    
                    if raw_material_found:
                        raw_material_found['quantity'] += required_quantity
                        raw_material_found['expected_quantity'] += expected_quantity
                        raw_material_found['quantity_b_f'] += current_quantity
                    else:
                        raw_materials.append(
                            {
                                'id': ing.minor_raw_material.id,
                                'name': ing.minor_raw_material.name,
                                'quantity_b_f': float(current_quantity),
                                'quantity': float(required_quantity),
                                'expected_quantity': float(expected_quantity),
                                'dish': item.dish.name,
                                'production_id': pp_id,
                                'accumulated_overrides_up':  total_overrides_up,
                                'accumulated_overrides_down':  total_overrides_down,
                            }
                        )
                    total_overrides_up = 0
                    total_overrides_down = 0
            logger.info(raw_materials)
            
        except Exception as e:
            messages.warning(request, f'{e}')

        return render(request, 'inventory/confirm_production_plan.html', 
            {
                'confirm': True,
                'production_plan': production_plan,
                'production_plan_items': production_plan_items,
                'total_cost_items': total_cost_items,
                'production_plan_minor_items': raw_materials,
                'dish_ing': dish_ingridients
            }
        )
    
@login_required
def overrideBf(request):
    if request.method == "GET":
        try:
            override_history = OverrideHistory.objects.filter(raw_material_overrided__branch=request.user.branch)
            o_history = []
            for items in override_history:
                o_history.append(
                    {
                        'date': items.date_overrided,
                        'raw_material': items.raw_material_overrided.name,
                        'up': items.up if items.up else 0,
                        'down': items.down if items.down else 0,
                    }
                )
            logger.info(o_history)
            return JsonResponse({'success':True, 'data': o_history}, status = 200)
        except Exception as e:
            return JsonResponse({'success':False, 'message': e}, status = 400)
    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            logger.info(data)
            logger.info(int(data.get('id')))
            product_info = Product.objects.get(id = int(data.get('id')), branch=request.user.branch)
            logger.info({'Product': product_info})

            production_raw_material_info = ProductionRawMaterials.objects.get(product = product_info)
            production_raw_material_info.quantity = float(data.get('new_quantity'))
            production_raw_material_info.save()

            override_formula = float(data.get('old_quantity')) - float(data.get('new_quantity'))
            logger.info(override_formula)

            if override_formula < 0:
                OverrideHistory.objects.create(
                    raw_material_overrided = product_info,
                    up = abs(override_formula)
                )
            else:
                OverrideHistory.objects.create(
                    raw_material_overrided = product_info,
                    down = override_formula
                )

            return JsonResponse({'success': True, 'messages': f'Updated {product_info.name} bf to {data.get('new_quantity')}'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error is {e}'})
    elif request.method == "DELETE":
        try:
            data = json.loads(request.body)
            logger.info(data)
            with transaction.atomic():
                for items in data:
                    print(items)
                    product_info = Product.objects.get(name = items, branch=request.user.branch)
                    production_raw_material = ProductionRawMaterials.objects.get(product = product_info)
                    production_raw_material.quantity = 0
                    production_raw_material.save()

                    override_history_clear = OverrideHistory.objects.filter(raw_material_overrided = product_info)
                    override_history_clear.delete()
                return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': e})
    else:
        return JsonResponse({'success': False, "message": 'Invalid request'}, status = 505)


@login_required      
@transaction.atomic
def process_production_plan_confirmation(request, pp_id):
    try:
        production_plan = Production.objects.select_related().get(id=pp_id, branch=request.user.branch)
        production_plan_items = ProductionItems.objects.filter(production=production_plan).select_related('raw_material')
    except Production.DoesNotExist:
        messages.warning(request, f'Production Plan With ID: {pp_id}, doesn\'t exist.')
        return redirect('inventory:process_production_plan', pp_id)
    
    with transaction.atomic():
        production_plan.status = True
        if production_plan.declared == True:
            production_plan.declared = False
        production_plan.save()
    messages.success(request, f'Production plan: {production_plan.production_plan_number.upper()}, successfully confirmed')
    return redirect('inventory:production_plans')


@login_required
def update_production_plan(request, pp_id):
    if request.method == 'GET':
        form = ProductionPlanInlineForm()
        try:
            production_plan = Production.objects.select_related().get(id=pp_id, branch=request.user.branch)
        except Production.DoesNotExist:
            messages.warning(request, f'Production Plan With ID: {pp_id}, doesn\'t exist.')

        return render(request, 'inventory/update_production_plan.html', 
            {
                'form':form,
                'production_plan':production_plan
            }
        )
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)
        
        production_plan_id = data['production_plan_id'] 
            
        try:
            production_plan = Production.objects.select_related().get(id=production_plan_id, branch=request.user.branch)
            production_plan_items = ProductionItems.objects.filter(production=production_plan).values(
                'raw_material__name'
                'dish__name'
                'quantity',
                'total_cost', 
                'rm_carried_forward_quantity',
                'lf_carried_forward_quantity',
                'actual_quantity',
                'production_completion_time'
            )
        except Production.DoesNotExist:
            return JsonResponse({'success': False, 'messages': f'Production plan wit ID: {production_plan_id} doesn\'t exists.'})
        
        return JsonResponse(list(production_plan_items), safe=False)


@login_required
def declare_production_plan(request, pp_id):
    if request.method == 'GET':
        try:
            production_plan = Production.objects.select_related().get(id=pp_id, branch=request.user.branch)
            production_plan_items = ProductionItems.objects.filter(production=production_plan)
            allocated_raw_materials = AllocatedRawMaterials.objects.filter(production=production_plan)
            
            raw_materials = []
            dish_raw = []
            for item in production_plan_items:
                for ing in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch):
                    
                    for all_raw_m in allocated_raw_materials:
                        if ing.minor_raw_material.id == all_raw_m.raw_material.id:
                            dish_entry = next((item for item in dish_raw if item['Name'] == ing.dish.name), None)

                            if dish_entry:
                                dish_entry['Ingredients'].append(
                                    {
                                        'Name': ing.minor_raw_material.name,
                                        'Quantity': f'{round(ing.quantity/ing.dish.portion_multiplier, 3)} {ing.minor_raw_material.unit}',
                                        'Planned': f'{round(all_raw_m.quantity/round(ing.quantity/ing.dish.portion_multiplier, 3))} Portion(s)'
                                    }
                                )
                            else:
                                dish_raw.append({
                                    'Name': ing.dish.name,
                                    'Ingredients': [
                                        {
                                            'Name': ing.minor_raw_material.name,
                                            'Quantity': f'{round(ing.quantity/ing.dish.portion_multiplier, 3)} {ing.minor_raw_material.unit}',
                                            'Planned': f'{round(all_raw_m.quantity/round(ing.quantity/ing.dish.portion_multiplier, 3))} Portion(s)'
                                        }
                                    ]
                                })
                            break

                    p_r_m_bf, created = ProductionRawMaterials.objects.get_or_create(
                        product=ing.minor_raw_material,
                        defaults={
                            'quantity': 0
                        } 
                    )
                    
                    quantity = ing.quantity * (item.portions / item.dish.portion_multiplier)
                    
                    raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)
                    
                    if raw_material_found:
                        
                        raw_material_found['quantity'] += quantity
                    else:
                        
                        raw_materials.append(
                            {
                                'id': ing.minor_raw_material.id,
                                'name': ing.minor_raw_material.name,
                                'quantity': float(quantity),
                            }
                        )
        except Production.DoesNotExist:
            messages.warning(request, f'Production Plan With ID: {pp_id} doesn\'t exist.')
            return redirect('inventory:production_plan_detail', pp_id)
        
        return render(request, 'inventory/declare_raw_material_left.html', {
            'production_plan': production_plan,
            'raw_materials': raw_materials,
            'allocated':allocated_raw_materials,
            'dish_raw': dish_raw
        })
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
    
            pp_item_id = data.get('production_plan_item')
            raw_material_used = float(data.get('quantity_used'))
            raw_material_id = data.get('raw_material_id')
            
            if not pp_item_id:
                return JsonResponse({'success': False, 'message': 'Missing Data: Production plan item'}, status=400)
            
            if raw_material_used is None:
                return JsonResponse({'success': False, 'message': 'Missing Data: Raw Material quantity used'}, status=400)
            
            try:
                production= Production.objects.get(id=pp_item_id, branch=request.user.branch)
            except ProductionItems.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'Production Plan with ID: {pp_item_id} doesn\'t exist'}, status=404)
            
            try:
                allocated = AllocatedRawMaterials.objects.get(raw_material__id=int(raw_material_id), production=production)
            except ProductionItems.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'Raw Material with ID: {raw_material_id } doesn\'t exist'}, status=404)

        
            p_rm = ProductionRawMaterials.objects.get(product__id=raw_material_id)
            p_rm.quantity -= raw_material_used
            
            
            allocated.remaining_quantity = allocated.quantity - raw_material_used
            allocated.save()
            
            ProductionLogs.objects.create(
                user=request.user, 
                action= 'declared',
                description='from warehouse',
                product=p_rm,
                quantity=p_rm.quantity,
                total_quantity=p_rm.quantity,
                branch=request.user.branch
            )
            p_rm.save()
            
            return JsonResponse({'success': True}, status=201)
        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def production_plan_delete(request, id):
    try:
        p_p_delete = Production.objects.get(id = id, branch=request.user.branch)
        p_p_delete.delete()
        messages.success(request, f'Successfully deleted production plan with id :{id}')
        return redirect('inventory:production_plans')
    except Exception as e:
        messages.warning(request, e)
        return redirect('inventory:production_plans')


def editProdPlan(prod_id, data):
    production_plan =  Production.objects.get(id = prod_id, branch=request.user.branch)

    for items in data:
        try:
            with transaction.atomic():
                pplan_items = ProductionItems.objects.get(production = production_plan, dish__name = items['name'].split('@')[0].strip())
                pplan_items.planned_portions = items['planned_portions']
                pplan_items.portions = items['portions']
                 
                pplan_items.save()

                logger.info(items['name'].split('@')[0].strip())
        except Exception as e:
            return print(f'Encountered an error: {e}')
        
    production_plan.status = False
    production_plan.save()
    
    return print(f'Successfully completed')


@login_required
def new_declare_production(request, pp_id):
    # pp_id = 25
    if request.method == 'GET':
        try:
            production_plan = Production.objects.select_related().get(id=pp_id, branch=request.user.branch)
            form = ProductionPlanInlineForm()
            production_plan_items = ProductionItems.objects.filter(production=production_plan)
            allocated_raw_materials = AllocatedRawMaterials.objects.filter(production=production_plan)
            print(allocated_raw_materials)
            
            raw_materials = []
            dish_details = []
            allocated_raw_materials = []
            total_cost = 0
            total_price = 0
            total_portions = 0

            for item in production_plan_items:
                    total_portions += item.portions
                    dish_details.append(
                        {
                            'name': item.dish.name,
                            'cost': item.dish.cost,
                            'total_price': round(item.dish.price * Decimal(item.portions), 2)
                        }
                    )
                    total_price += round(item.dish.price * Decimal(item.portions), 2)
                    for ing in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch):
                        
                        p_r_m_bf, created = ProductionRawMaterials.objects.get_or_create(
                            product=ing.minor_raw_material,
                            defaults={
                                'quantity': 0
                            } 
                        )
                        
                        quantity = round(ing.quantity * (item.portions / item.dish.portion_multiplier), 3)
                        print(quantity)
                        raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)
                        
                        if raw_material_found:
                            
                            raw_material_found['quantity'] += round(float(quantity), 3)
                            raw_material_found['cost'] = round(Decimal(raw_material_found['quantity']) * ing.minor_raw_material.cost, 2)
                        else:
                            
                            raw_materials.append(
                                {
                                    'id': ing.minor_raw_material.id,
                                    'name': ing.minor_raw_material.name,
                                    'quantity': round(float(quantity), 3),
                                    'unit': ing.minor_raw_material.unit.unit_name,
                                    'cost': round(Decimal(ing.minor_raw_material.cost) * Decimal(quantity), 2),
                                }
                            )
                        
                        raw_material_prod = Product.objects.get(id = ing.minor_raw_material.id)


                        raw_material_prod_found = next((rm for rm in allocated_raw_materials if rm['id'] == raw_material_prod.id), None)

                        if raw_material_prod_found:
                            logger.info('FOUND')
                        else:
                            allocated_raw_materials.append(
                                {
                                    'id': raw_material_prod.id,
                                    'name': raw_material_prod.name,
                                    'quantity': round(float(raw_material_prod.quantity), 3),
                                    'unit': raw_material_prod.unit.unit_name,
                                    'cost': round(Decimal(raw_material_prod.cost) * Decimal(raw_material_prod.quantity), 2),
                                }
                            )
      
            allocated_raw_material_total_cost = 0
            allocated_raw_material_total_qnty = 0
            
            for items in allocated_raw_materials:
                allocated_raw_material_total_cost += items['cost']
                allocated_raw_material_total_qnty += items['quantity']

            for cost in raw_materials:
                total_cost += cost['cost']

        except Production.DoesNotExist:
            messages.warning(request, f'Production Plan With ID: {pp_id} doesn\'t exist.')
            return redirect('inventory:production_plan_detail', pp_id)
        
        return render(request, 'inventory/new_declare.html', {
            'p_plan': production_plan,
            'production_plan': production_plan_items,
            'ingridients':raw_materials,
            'allocated': allocated_raw_materials,
            'production_plan_id': pp_id,
            'total_price': dish_details,
            'total': total_cost,
            'total_portions': total_portions,
            'price': total_price,
            'form': form,
            'all_r_m_cost':allocated_raw_material_total_cost,
            'all_r_m_qnty':allocated_raw_material_total_qnty,
        })
        
    elif request.method == 'POST':
        data = json.loads(request.body)

        dish_name = data.get('dish_name').split('@')[0].strip()
        logger.info(f'Dish Name: {dish_name}')
        portions = data.get('portions')

        try:
            dish_ing = Ingredient.objects.filter(dish__name = dish_name, minor_raw_material__branch=request.user.branch)
            logger.info(f'Dish ingridients: {dish_ing}')

            ingridient_list = []

            for ingridient in dish_ing:
                portion_m = ingridient.dish.portion_multiplier
                qnty = ingridient.quantity

                prop = qnty/portion_m
                declared_total_qnty = prop * int(portions)
                logger.info({'Name': ingridient.minor_raw_material.name, 'Declared Qnty': declared_total_qnty})
                ingridient_list.append({
                    'ingridient_name': ingridient.minor_raw_material.name,
                    'ingridient_qnty': round(declared_total_qnty, 3)
                })
                
            productiont = Production.objects.get(id=pp_id, branch=request.user.branch)
            production_item = ProductionItems.objects.get(production=productiont, dish__name=dish_name)
            
            logger.info(f'production {production_item.planned_portions}')

            # update eod_item
            eod, created = EndOfDay.objects.get_or_create(date=datetime.datetime.now(), branch=request.user.branch, done=False)
            eod_item = EndOfDayItems.objects.filter(end_of_day=eod, dish_name=dish_name).first()
            eod_item.declared = float(portions)
            eod_item.expected = production_item.portions
            logger.info(f'Planned portitions: {production_item.portions}')
            eod_item.save()
            
            logger.success(f'Successfully updated EOD item for dish: {dish_name} with declared portions: {portions}')
            
            return JsonResponse({'success':True, 'ingridient': ingridient_list}, status = 200)
        except Exception as e:
            logger.error(f'Error: {e}')
            return JsonResponse({'success': False}, status= 400)
        
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            ing_data = data.get('data', '')
            dish_data = data.get('data_dish', '')
            
            logger.info({
                'ING': ing_data,
                'DISH': dish_data
            })

            try:
                production= Production.objects.get(id=pp_id, branch=request.user.branch)
            except ProductionItems.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'Production Plan with ID: {pp_id} doesn\'t exist'}, status=404)

            edit_pplan_portions = []

            for ing in ing_data:
                logger.info({
                    'name': ing.get('ingridient_name'),
                    'used_qnty': ing.get('system'),
                    'variance': ing.get('variance')
                })
            
                # try:
                #     allocated = AllocatedRawMaterials.objects.get(raw_material__name=ing.get('ingridient_name'), production=production)
                # except ProductionItems.DoesNotExist:
                #     return JsonResponse({'success': False, 'message': f'Raw Material with ID: {ing.get('ingridient_name')} doesn\'t exist'}, status=404)

                try:
                    product = Product.objects.get(name=ing.get('ingridient_name'), branch=request.user.branch)
                    p_rm_variance = ProductionVariance.objects.create(
                        production=production,
                        ingredient=product,
                        quantity=float(ing.get('variance'))
                    )
                    logger.info(p_rm_variance)
                except ProductionVariance.DoesNotExist:
                    return JsonResponse({'success': False, 'message': f'Variance for Raw Material with ID: {ing.get('ingridient_name')} doesn\'t exist'}, status=404)
                
                with transaction.atomic():
                    p_rm = ProductionRawMaterials.objects.get(product__name=ing.get('ingridient_name'))
                    p_rm.quantity -= float(ing.get('system'))
                    
                    
                    # allocated.remaining_quantity = allocated.quantity - float(ing.get('system'))
                    # allocated.save()
                    
                    ProductionLogs.objects.create(
                        user=request.user, 
                        action= 'declared',
                        description='from warehouse',
                        product=p_rm,
                        quantity=p_rm.quantity,
                        total_quantity=p_rm.quantity,
                    )
                    p_rm.save()
    
            try:
                production = Production.objects.get(id=pp_id, branch=request.user.branch)  
                production_plan_items = ProductionItems.objects.filter(production=production)
                total_cost = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
            except Production.DoesNotExist:
                return JsonResponse({'success':False, 'message':f'Production with ID: {pp_id}, doesn\'t exists'})
      
            declaration_flag = True
            with transaction.atomic():
                COGS.objects.create(
                    production=production,
                    amount=total_cost,
                    # branch=request.user.branch
                )
                
                if declaration_flag:
                    
                    production.declared = True
                    production.save()
            
            for dish in dish_data:
                logger.info({
                    'name': dish.get('dish_name'),
                    'p_portions': dish.get('planned_portions'),
                    'declared': dish.get('declared'),
                    'note': dish.get('note', '')
                })
                if dish.get('note'):
                    note = dish.get('note', '')
                    extra_portions = Decimal(note.split(':')[1].strip())
                    edit_pplan_portions.append(
                        {
                            'name': dish.get('dish_name'),
                            'portions': dish.get('declared'),
                            'planned_portions': dish.get('planned_portions'),
                            'add_portions': extra_portions
                        }
                    )

            logger.info(edit_pplan_portions)
            if edit_pplan_portions:
                editProdPlan(prod_id=pp_id, data=edit_pplan_portions)

            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f'Error: {e}')
            return JsonResponse({'success':False})


@login_required
def latest_declare_production(request):
    if request.method == 'GET':
        try:
            latest_declared_plan = (
                Production.objects
                .filter(declared=True, branch=request.user.branch)
                .order_by('-date_created', '-time_created')
                .select_related()
                .first()
            )
            pr_variance = ProductionVariance.objects.filter(production=latest_declared_plan).select_related('ingredient')

            if not latest_declared_plan:
                return JsonResponse({'success': False, 'message': 'No declared production plan found.'}, status=404)

            pr_variance = ProductionVariance.objects.filter(production=latest_declared_plan).select_related('ingredient')
            production_plan_items = ProductionItems.objects.filter(production=latest_declared_plan)

            raw_materials = []
            raw_material_variance = []
            dish_details = []
            dishes_serialized = []
            total_cost = Decimal(0)
            total_price = Decimal(0)
            total_portions = 0


            for item in pr_variance:
                existing = next((rm for rm in raw_material_variance if rm['name'] == item.ingredient.name), None)
                if existing:
                    existing['quantity'] += float(item.quantity)
                    existing['cost'] = float(item.ingredient.cost)
                    existing['total_cost'] += float(item.quantity * float(item.ingredient.cost))
                else:
                    raw_material_variance.append({
                        'name': item.ingredient.name,
                        'quantity': float(item.quantity),
                        'cost': float(item.ingredient.cost),
                        'total_cost': float(item.quantity * float(item.ingredient.cost))
                    })

            for item in production_plan_items:
                total_portions += item.portions

                dish_total_price = round(item.dish.price * Decimal(item.portions), 2)
                total_price += dish_total_price

                dishes_serialized.append({
                    'dish': {
                        'name': item.dish.name,
                        'price': float(item.dish.price),
                        'cost': float(item.dish.cost),
                        'portion_multiplier': float(item.dish.portion_multiplier)
                    },
                    'portions': item.portions
                })

                dish_details.append({
                    'name': item.dish.name,
                    'cost': float(item.dish.cost),
                    'total_price': float(dish_total_price)
                })

                ingredients = Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch)
                for ing in ingredients:
                    quantity = round(ing.quantity * (item.portions / item.dish.portion_multiplier), 3)

                    existing = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)

                    if existing:
                        existing['quantity'] += round(float(quantity), 3)
                        existing['cost'] = round(Decimal(existing['quantity']) * ing.minor_raw_material.cost, 2)
                    else:
                        raw_materials.append({
                            'id': ing.minor_raw_material.id,
                            'name': ing.minor_raw_material.name,
                            'quantity': round(float(quantity), 3),
                            'unit': ing.minor_raw_material.unit.unit_name,
                            'cost': round(Decimal(ing.minor_raw_material.cost) * Decimal(quantity), 2)
                        })

            for rm in raw_materials:
                total_cost += rm['cost']

            data_content = {
                'production_plan': dishes_serialized,
                'total_price': dish_details,
                'ingridients': raw_materials,
                'production_plan_id': latest_declared_plan.id,
                'total': float(round(total_cost, 2)),
                'total_portions': total_portions,
                'price': float(round(total_price, 2)),
                'raw_material_variance': raw_material_variance,
            }

            return JsonResponse({'success': True, 'data': data_content}, status=200)

        except Exception as e:
            logger.error(f"Error in latest_declare_production: {e}")
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@login_required
def production_raw_materials(request):
    raw_materials = ProductionRawMaterials.objects.filter(product__branch=request.user.branch)
    return render(request, 'inventory/production_rm.html', {'raw_materials':raw_materials})


@login_required
def confirm_declaration(request):
    if request.method == 'POST':
        # payload
        """
            production_plan:id (int)
        """
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)
        
        pp_id = data.get('production_plan')
        
        if not pp_id:
            return JsonResponse({'success': False, 'message': 'Missing Data: Production Plan ID'}, status=400)
        
        try:
            production = Production.objects.get(id=pp_id, branch=request.user.branch)  
            production_plan_items = ProductionItems.objects.filter(production=production)
            total_cost = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
        except Production.DoesNotExist:
            return JsonResponse({'success':False, 'message':f'Production with ID: {pp_id}, doesn\'t exists'})
        
        declaration_flag = True
        
        COGS.objects.create(
            production=production,
            amount=total_cost,
            branch=request.user.branch
        )
        
        if declaration_flag:
            
            production.declared = True
            production.save()
            
            return JsonResponse(
                {
                    'success':True, 
                    'message':f'Production Plan: {production.production_plan_number} successfully declared'
                }
            )
        else:
            return JsonResponse(
                {
                    'success':False, 
                    'message':f'Production Plan: {production.production_plan_number} declaration failed, Plesase check if you have declared each line'
                }
            )
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@login_required
def raw_material_json(request):
    try:
        data = json.loads(request.body)
        raw_material_id = data.get('raw_material_id')
        
        r_m = Product.objects.filter(id=raw_material_id, branch=request.user.branch).values(
            'cost',
            'unit__unit_name'
        )
        r_m = list(r_m)
    
        return JsonResponse({'success':True, 'data':r_m})
    except Exception as e:
        return JsonResponse({'success': False, 'message':f'{e}'})
    
    
class DishListView(View):
    def get(self, request):
        dishes = Dish.objects.filter(branch=request.user.branch)
        ingredients = Ingredient.objects.filter(minor_raw_material__branch=request.user.branch)

        # if download:
        #     logger.info('download')
        #     response = HttpResponse(content_type='text/csv')
        #     response['Content-Disposition'] = f'attachment; filename="_{filter_option}.csv"'

        #     writer = csv.writer(response)
        #     writer.writerow(['Date', 'Description', 'Done By', 'Amount'])

        #     total_expense = 0  
        #     for expense in expenses:
        #         total_expense += expense.amount

        #         writer.writerow([
        #             expense.date,
        #             expense.description,
        #             expense.user.first_name,
        #             expense.amount,
        #         ])

        #     writer.writerow(['Total', '', '', total_expense])
        
            # return response
        logger.info(ingredients)
        return render(request, 'inventory/dish_list.html', 
            {
                'dishes': dishes,
                'ingredients':ingredients
            }
        )
    
# to remove
def p_home(request):
    return render(request, 'inventory/production_home.html')
    
class DishCreateView(View):
    def get(self, request):
        form = DishForm()
        r_m = Product.objects.filter(raw_material=True, branch=request.user.branch)
        packaging_products = Product.objects.filter(packaging=True, branch=request.user.branch)
        
        return render(request, 'inventory/dish_form.html', {
            'form': form, 
            'r_m':r_m,
            'packaging_products':packaging_products
        })

    def post(self, request):
        form = DishForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('inventory:dish_list')
        return render(request, 'inventory/dish_form.html', {'form': form})

class DishUpdateView(View):
    
    def get(self, request, pk):
        dish = get_object_or_404(Dish, pk=pk, branch=request.user.branch)
        dish_form = DishForm(instance=dish)
        return render(request, 'inventory/dish_form.html', {'dish_form': dish_form, 'dish': dish})
        dish_form = DishForm(instance=dish)
        return render(request, 'inventory/dish_form.html', {'dish_form': dish_form, 'dish': dish})

    def post(self, request, pk):
        dish = get_object_or_404(Dish, pk=pk, branch=request.user.branch)
        form = DishForm(request.POST, instance=dish)
        if form.is_valid():
            form.save()
            return redirect('inventory:dish_list')
        return render(request, 'inventory/dish_form.html', {'form': form, 'dish': dish})

class DishDeleteView(View):
    
    def get(self, request, pk):
        dish = get_object_or_404(Dish, pk=pk, branch=request.user.branch)
        dish.delete()
        return redirect('inventory:dish_list')

# Ingredient Views
class IngredientListView(View):
    
    def get(self, request):
        ingredients = Ingredient.objects.filter(minor_raw_material__branch=request.user.branch)
        return render(request, 'inventory/ingredient_list.html', {'ingredients': ingredients})

class IngredientCreateView(View):
    
    def get(self, request):
        form = IngredientForm()
        return render(request, 'inventory/ingredient_form.html', {'form': form})

    def post(self, request):
        form = IngredientForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('inventory:ingredient_list')
        return render(request, 'inventory/ingredient_form.html', {'form': form})

class IngredientUpdateView(View):
    
    def get(self, request, pk):
        ingredient = get_object_or_404(Ingredient, pk=pk, minor_raw_material__branch=request.user.branch)
        form = IngredientForm(instance=ingredient)
        return render(request, 'inventory/ingredient_form.html', {'form': form, 'ingredient': ingredient})

    def post(self, request, pk):
        ingredient = get_object_or_404(Ingredient, pk=pk, minor_raw_material__branch=request.user.branch)
        form = IngredientForm(request.POST, instance=ingredient)
        if form.is_valid():
            form.save()
            return redirect('inventory:ingredient_list')
        return render(request, 'inventory/ingredient_form.html', {'form': form, 'ingredient': ingredient})

class IngredientDeleteView(View):
    
    def get(self, request, pk):
        ingredient = get_object_or_404(Ingredient, pk=pk, minor_raw_material__branch=request.user.branch)
        ingredient.delete()
        return redirect('inventory:ingredient_list')
    

@login_required
def add_dish(request): # didn't change the name of the template, it caters for both, dish and ingredient creation
    form = IngredientForm()
    dish_form = DishForm()
    
    if request.method == 'GET':
        r_m = Product.objects.filter(raw_material=True, branch=request.user.branch)
        return render(request, 'inventory/ingredient_form.html', 
            {
                'r_m':r_m,
                'form':form,
                'dish_form':dish_form,
                'packaging_products':packagaging_products
            }
        )
    
    if request.method == 'POST':
        # payload
        """
        {
            name:str
            portion_multiplier:float
            cost:float
            category:str
            
            "cart": [
                {
                    "name":(str)
                    "raw_material": name (str),
                    "quantity": int,
                    "dish_id": id (int)
                }
            ]
        }
        """
        
        try:
            data = json.loads(request.body)
           
            cart = data.get('dish_info', [])
            cost = data.get('dish_cost')
            supplies = data.get('supplies', [])
            ingredients = data.get('ingredients', [])

            logger.info(data)
            
            products = Product.objects.filter(packaging=True, branch=request.user.branch)
            products_map = { product.name:product for product in products }
            
            with transaction.atomic():
 
                dish = Dish.objects.create(
                    cost = cost,
                    name = cart['name'],
                    portion_multiplier = cart['portion_multiplier'],
                    price = cart['selling_price'],
                    category=cart['category'],
                    branch=request.user.branch
                )
                
                logger.success(f'Dish-{dish.name} saved')
                
                for supply in supplies:
                    print(supply['item'])
                    product = products_map.get(supply['item'])
                    Supplies.objects.create(
                        item = product,
                        dish = dish,
                        
                        quantity = supply['quantity'],
                        type='dish'
                    )
                    
                logger.success(f'Supplies saved')

                for item in ingredients:
                    raw_material = Product.objects.get(name=item.get('raw_material'), branch=request.user.branch)
                    Ingredient.objects.create(
                        dish=dish,
                        note=item.get('note'),
                        minor_raw_material=raw_material,
                        quantity=item.get('quantity'),
                        cost=item.get('cost'),
                        # branch=request.user.branch
                    )

        except Exception as e:
            logger.error(f'Error saving dish: {e}')
            return JsonResponse({'success':False, 'message':f'{e}'})
        return JsonResponse({'success':True, 'meessage':f'Ingridient successfully added'})


@login_required
def meal_list(request):
    meals = Meal.objects.filter(deactivate=False, branch=request.user.branch)
    dish_list = []
    dish_count =  0
    logger.info(meals)

    
    for meal in meals:
        for dish in meal.dish.all():
            dish_name = dish.name
            logger.info(dish_name)

            found = False
            for item in dish_list:
                if item['Name'] == meal.name:
                    item['Cost'] += dish.cost
                    gp = ((Decimal(meal.price) - item['Cost']) / Decimal(meal.price)) * Decimal(100)
                    item['GP'] = gp.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    found = True
                    break
            if not found:
                gp = ((Decimal(meal.price) - dish.cost) / Decimal(meal.price)) * Decimal(100)
                dish_list.append({
                    'Name': meal.name,
                    'Cost': Decimal(dish.cost),
                    'Selling': Decimal(meal.price),
                    'GP': gp.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                })

    logger.info(dish_list)

    return render(request, 'inventory/meal_list.html', 
        {
            'meals':meals,
            'meals_info': dish_list
        }
    )

@login_required
def add_meal(request):
    dishes = Dish.objects.filter(branch=request.user.branch)
    meal_categories = MealCategory.objects.all()
    
    if request.method == 'POST':
        form = MealForm(request.POST)

        if form.is_valid():
            name = form.cleaned_data['name']
            price = form.cleaned_data['price']
            category = form.cleaned_data['category']
            selected_dishes = request.POST.getlist('dish')
            selected_supplies = request.POST.getlist('supplies')
            
            logger.info(f'supplies: {selected_supplies}')

            if Meal.objects.filter(name__iexact=name).exists():
                messages.warning(request, f'Meal "{name.upper()}" already exists.')
                return redirect('inventory:add_meal')

            if float(price) < 0:
                messages.warning(request, 'Price cannot be less than zero.')
                return redirect('inventory:add_meal')

            meal = form.save(commit=False)
            meal.branch = request.user.branch
            meal.save()

            if selected_dishes:
                meal.dish.set(selected_dishes)

            for product_id in selected_supplies:
                product = Product.objects.filter(id=product_id, branch=request.user.branch).first()
                if product:
                    Supplies.objects.create(
                        meal=meal,
                        item=product,
                        quantity=1,  # to be dynamic
                    )
            messages.success(request, f'Meal "{meal.name}" created successfully.')
            return redirect('inventory:meal_list')
        else:
            messages.error(request, 'Please correct the errors in the form.')
            logger.error(f"Form errors: {form.errors}")

    else:
        form = MealForm()

    return render(request, 'inventory/add_meal.html', 
        {
            'dishes':dishes,
            'meal_categories':meal_categories,
            'packaging_products':Product.objects.filter(packaging=True, branch=request.user.branch),
            'form': form
        }
    )

@login_required
def get_dish_data(request, dish_id):
    try:
        dish = Dish.objects.filter(id=dish_id, branch=request.user.branch).values(
            'name',
            'cost',
            'price',
            'category',
            'portion_multiplier'
        )
        ingredients =Ingredient.objects.filter(dish__id = dish_id, minor_raw_material__branch=request.user.branch).values(
            'note',
            'quantity',
            'minor_raw_material__name',
            'minor_raw_material__cost'
        )

        return JsonResponse({'success':True, 'dish':list(dish), 'ingridients':list(ingredients)})

    except Exception as e:
        return JsonResponse({'success':False, 'message':f'{e}'})

@login_required
def edit_dish(request, dish_id):
    if request.method == 'GET':
        try:
            dish = Dish.objects.get(id=dish_id, branch=request.user.branch)
            dish_form = DishForm()
            r_m = Product.objects.filter(raw_material=True, branch=request.user.branch)

            return render(request, 'inventory/edit_dish.html',{
                'r_m':r_m,
                'dish':dish,
                'dish_form': dish_form
            })
        except:
            return JsonResponse({'success':False, 'message':f'Dish not found'})
        
    if request.method == 'POST':
        try:

            dish_name = request.POST.get('name')
            cost = request.POST.get('dish_cost')
            selling_price = request.POST.get('selling_price')
            portion_multiplier = request.POST.get('portion_multiplier')
            category = request.POST.get('category')
            image = request.FILES.get('image')
            cart = json.loads(request.POST.get('cart'))

            """
            data = json.loads(request.body)
            cart = data.get('cart', [])
            
            logger.info(f'cart: {cart}')
            
            dish_name = data.get('name')
            portion_multiplier = data.get('portion_multiplier')
            cost = data.get('dish_cost')
            selling_price = data.get('selling_price')
            category = data.get('category')
            image = data.get('image')
            """

            logger.info(f'cart: {cart}')
            logger.info(image)


            cat, _= MealCategory.objects.get_or_create(name=category) 
            dish = Dish.objects.get(id=dish_id)
            logger.info(f'Dish name: {dish_name}')
            dish.name = dish_name
            dish.portion_multiplier = portion_multiplier
            dish.cost = cost
            dish.price = selling_price
            dish.category = dish.category
            # dish.image = image
            existing_ingredients = Ingredient.objects.filter(dish=dish, minor_raw_material__branch = request.user.branch)
            existing_ingredient_names = {ing.minor_raw_material.name for ing in existing_ingredients}
            raw_material_map = {rm.name: rm for rm in Product.objects.filter(branch = request.user.branch)}

            ingredient_updates = []
            ingredients_to_delete = existing_ingredients[:]

            for item in cart:
                raw_material_name = item['raw_material']
                raw_material = raw_material_map.get(raw_material_name)

                if not raw_material:
                    return JsonResponse({'success': False, 'message': f'Raw material "{raw_material_name}" not found.'})

                if raw_material_name in existing_ingredient_names:
                    ing = next(ing for ing in existing_ingredients if ing.minor_raw_material.name == raw_material_name)
                    ing.quantity = item['quantity']
                    ing.note = item['note']
                    ingredient_updates.append(ing)

                    ingredients_to_delete.remove(ing)
                else:
                    ingr = Ingredient.objects.create(
                        dish=dish,
                        minor_raw_material=raw_material,
                        quantity=item['quantity'],
                        note=item['note'],
                    )
                    logger.info(f'Added ingredient: {ingr}')

            if ingredients_to_delete:
                logger.info(f'Deleting ingredients: {ingredients_to_delete}')
                Ingredient.objects.filter(id__in=[ing.id for ing in ingredients_to_delete], minor_raw_material__branch = request.user.branch).delete()

            if ingredient_updates:
                logger.info(f'Updating ingredients: {ingredient_updates}')
                with transaction.atomic():
                    Ingredient.objects.bulk_update(ingredient_updates, fields=['quantity', 'note'])

            dish.save()
            return JsonResponse({'success': True}, status=200)

        except Exception as e:
            logger.error(f'Error processing request: {e}')
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
        
    return JsonResponse({'success':False, 'message':'Invalid request'}, status=500)

@login_required
def edit_meal(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id, branch=request.user.branch)
    meal_categories = MealCategory.objects.all()
    dishes = Dish.objects.filter(branch=request.user.branch)
    if request.method == 'POST':
        form = MealForm(request.POST, request.FILES, instance=meal)
        if form.is_valid():
            name = form.cleaned_data['name']
            price = form.cleaned_data['price']
            
            # validation
            if float(price) < 0:
                messages.warning(request, f'Price can\'t be less than zero.')
                return redirect('inventory:add_meal')
            
            form.save()
            logger.info('saved')
            # return redirect('inventory:meal_list')
            return JsonResponse({'success': True}) 
    else:
        form = MealForm(instance=meal)

    return render(request, 'inventory/edit_meal.html', 
        {
            'form': form, 
            'meal': meal,
            'meal_categories': meal_categories,
            'dishes': dishes
        }
    )


@login_required
def delete_meal(request, meal_id):
    try:
        meal = Meal.objects.get(id=meal_id, branch=request.user.branch)
        meal.deactivate = True
        meal.save()
        return JsonResponse({'success': True}, status=200)
    except Meal.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Meal does not exist'}, status=400)



@login_required
def create_meal_category(request):
    if request.method == 'GET':
        categories = MealCategory.objects.all().values()
        product_categories = Product.objects.filter(finished_product=True, branch = request.user.branch).values('category__name', 'category__id')
        dish_categories = Dish.objects.filter(dish=True, branch = request.user.branch).values()

        meal_category_list = []
        product_category_list = []
        dish_category_list = []

        for items in categories:
            meal_category_list.append(items)

        for items in product_categories:
            product_category_list.append(items)
        
        for items in dish_categories:
            dish_category_list.append(items)

        return JsonResponse({'product':product_category_list, 'meal':meal_category_list, 'dish': dish_category_list}, safe=False, status = 200)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            category_name = data.get('category')
            
            if category_name:
                category, created = MealCategory.objects.get_or_create(name=category_name)
                if created:
                    return JsonResponse({'success': True, 'id': category.id, 'name': category.name}, status=201)
                else:
                    return JsonResponse({'success': False, 'message': 'Category already exists'}, status=400)
                
            return JsonResponse({'success': False, 'message': 'Invalid data'}, status=405)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'{e}'}, status=400)

@login_required
def CategoryMeal(request):
    if request.method == 'GET':
        category_name = request.GET.get('category')
        logger.info(category_name)
        
        meal_filter = Meal.objects.filter(category__name = category_name, deactivate = False, branch = request.user.branch).values('id', 'name', 'price', 'image', 'meal')
        product_filter = Product.objects.filter(category__name = category_name, finished_product=True, branch = request.user.branch).values('id', 'name', 'quantity', 'price', 'finished_product', 'image')
        dish_filter = Dish.objects.filter(category = category_name, branch = request.user.branch).values('id', 'name', 'price', 'dish', 'image')

        if not meal_filter and not dish_filter:
            product_data = [
                {
                    "id": f'p-{product['id']}',
                    "name": product['name'],
                    "quantity": product['quantity'],
                    "price": product['price'],
                    "finished_product": product['finished_product'],
                    "image": product['image']
                }
                for product in product_filter
            ]
            return JsonResponse(product_data, safe=False, status = 200)
        else:
            dish_data = [
                {
                    "id": f'd-{dish['id']}',
                    "name": dish['name'],
                    "price": dish['price'],
                    "dish": dish['dish'],
                    "image": dish['image']
                }
                for dish in dish_filter
            ]
        
            meal_data = [
                {
                    "id": f'm-{meal['id']}',
                    "name": meal['name'],
                    "price": meal['price'],
                    "meal": meal['meal'],
                    "image": meal['image']
                }
                for meal in meal_filter
            ]

            final_data = meal_data + dish_data
            return JsonResponse(final_data, safe=False, status = 200)
    elif request.method == 'POST':
        categories = ['BEEF', 'CHICKEN', 'SALAD', 'SADZA', 'RICE', 'SPAGHETTI', 'MACARONI']
        return JsonResponse({'success': True, 'categories': categories})
    else:
        return JsonResponse({'sucess': False, 'message': 'Invalid request'}, status = 500)

@login_required
def end_of_day_pdf(request):
    if request.method == "GET":
        today = localdate()

        e_o_d = EndOfDay.objects.filter(date=today, done=True, branch = request.user.branch).first()

        if not e_o_d:
            messages.warning(request,'No end of day completed')
            return HttpResponse("No completed End Of Day report for today.", status=404)

        e_o_d_items = EndOfDayItems.objects.filter(end_of_day=e_o_d)
        dish_items = Dish.objects.all()

        logger.info(list(e_o_d_items))

        e_o_d_items_list = [
            {
                'Name': item.dish_name,
                'Total_Portions': item.total_portions,
                'Sold': item.total_sold,
                'Staff_Portions': item.staff_portions,
                'Wastage': item.wastage,
                'Leftovers': item.leftovers,
                'Expected': item.expected
            }
            for item in e_o_d_items
        ]

        dish_items_list = []
        total_list = []

        for items in dish_items:
            for item in e_o_d_items_list:
                if items.name == item['Name']:
                    dish_items_list.append(
                        {
                            'Name': items.name,
                            'total_declared_cost': items.cost * item['Total_Portions'],
                            'total_sold_price': items.price * item['Sold'],
                            # 'total_sold_price': items.price * item['Sold'],
                            'total_staff_price': items.price * item['Staff_Portions'],
                            'total_wastage_price': items.price * Decimal(item['Wastage']),
                            'total_leftover_price': items.price * Decimal(item['Leftovers']),
                            'total_expected_price': items.price * Decimal(item['Expected']),
                        }
                    )

                    break
                else:
                    pass
        
        for item in dish_items_list:
            if total_list:
                total_list['declared'] += item['total_declared_cost']
                total_list['sold'] += item['total_sold_price']
                total_list['meal'] += item['total_staff_price']
                total_list['wastage'] += item['total_wastage_price']
                total_list['leftover'] += item['total_leftover_price']
                total_list['expected'] += item['total_expected_price']
            else:
                total_list.append(
                    {
                        'declared': item['total_declared_cost'],
                        'sold': item['total_sold_price'],
                        'meal': item['total_staff_price'],
                        'wastage': item['total_wastage_price'],
                        'leftover': item['total_leftover_price'],
                        'expected': item['total_expected_price']
                    }
                )

        logger.info(e_o_d_items_list)
        logger.info(dish_items_list)
        logger.info(total_list)
        gross_profit = 0
        for totals in total_list:
            if totals:
                gross_profit = (totals['sold'] + totals['leftover'])  - ( totals['declared'] + totals['meal'] + totals['wastage'])

        return render_to_pdf(
            template_src="End_of_day_pdf_report.html",
            context_data={"productions_today": e_o_d_items_list, 'dish_info': dish_items_list, 'totals': total_list, 'date': datetime.datetime.today(), 'gross_profit':gross_profit}
        )
    return JsonResponse({'success': False, "message": "Failed to download PDF"}, status = 500)

@login_required
def end_of_day_view_json(request):
    if request.method == 'GET':
        today = localdate()
        
        try:
            e_o_d = EndOfDay.objects.get(date=today, branch = request.user.branch)
        except EndOfDay.DoesNotExist:
            e_o_d = None

        productions_today = Production.objects.filter(date_created=today, declared=True, branch = request.user.branch)
        production_items_today = ProductionItems.objects.filter(production__in=productions_today, end_of_day_status = False)

        productions_today = production_items_today.values('dish__name').annotate(
            total_portions=Sum('portions'),
            total_sold=Sum('portions_sold'),
            total_staff_portions=Sum('staff_portions')
        )
        
        logger.info(productions_today)
        
        production_data = []
        for items in productions_today:
            production_data.append(
                {
                    'name': items['dish__name'],
                    'total_portions': items['total_portions'],
                    'total_sold': items['total_sold'],
                    'total_staff_portions': items['total_staff_portions']
                }
            )
        logger.info(production_data)

        return JsonResponse({'success':True, 'production_today': production_data}, status = 200)
    else:
        return JsonResponse({'success': False}, status = 400)

@login_required
def end_of_day_view(request):
    if request.method == 'GET':
        today = datetime.date.today()
        branch = request.user.branch

        sales_qs = SaleItem.objects.filter(
            sale__void=False,
            sale__date=today,
            sale__branch=branch
        )
        staff_sales_qs = sales_qs.filter(sale__staff=True)

        dish_sales_map = {}
        finished_products_map = {}
        staff_portions_map = {}

        for item in sales_qs:
            if item.meal:
                for dish in item.meal.dish.all():
                    dish_sales_map[dish.name] = dish_sales_map.get(dish.name, 0) + (item.quantity or 0)
            else:
                if item.dish:
                    name = item.dish.name
                    dish_sales_map[name] = dish_sales_map.get(name, 0) + (item.quantity or 0)
                else:
                    name = item.product.name
                    finished_products_map[name] = finished_products_map.get(name, 0) + (item.quantity or 0)

        for item in staff_sales_qs:
            if item.meal:
                for dish in item.meal.dish.all():
                    staff_portions_map[dish.name] = staff_portions_map.get(dish.name, 0) + (item.quantity or 0)
            else:
                
                if item.dish:
                    name = item.dish.name
                    staff_portions_map[name] = staff_portions_map.get(name, 0) + (item.quantity or 0)
                else:
                    name = item.product.name
                    finished_products_map[name] = finished_products_map.get(name, 0) + (item.quantity or 0)

        all_names = set(dish_sales_map.keys()) | set(staff_portions_map.keys())
        all_products = set(finished_products_map.keys())

        all_names = list(set(all_products) | set(all_names))

        production_today = []
        finished_goods_list = []
        for name in all_names:
            production_today.append({
                'sold': name,
                'total_portions': dish_sales_map.get(name, 0),
                'total_sold': dish_sales_map.get(name, 0),
                'total_staff_portions': staff_portions_map.get(name, 0),
            })
        
        for name in all_products:
            finished_goods_list.append({
                'sold': name,
                'total_portions': finished_products_map.get(name, 0),
                'total_sold': finished_products_map.get(name, 0),
                'total_staff_portions': 0,
            })

        e_o_d, created = EndOfDay.objects.get_or_create(
            date=today,
            branch=branch,
            done=False
        )

        existing_items = EndOfDayItems.objects.filter(end_of_day=e_o_d).values_list('dish_name', flat=True)

        items_to_process = [
            {
                'sold': dish['sold'],
                'is_product': False,
                'total_portions': dish['total_portions'] or 0,
                'total_sold': dish['total_sold'],
                'staff_portions': dish['total_staff_portions'],
            }
            for dish in production_today
        ] + [
            {
                'sold': product['sold'],
                'is_product': True,
                'total_portions': product['total_portions'] or 0,
                'total_sold': product['total_sold'],
                'staff_portions': 0,
            }
            for product in finished_goods_list
        ]

        for item in items_to_process:
            update_kwargs = {
                'total_portions': item['total_portions'],
                'total_sold': item['total_sold'],
                'staff_portions': item['staff_portions'],
            }
           
            if item['is_product']:
                update_kwargs['finished_product'] = item['sold']
                print('finished product ->', item['sold'])
            if item['sold'] not in existing_items:
                logger.info(f"Creating EndOfDayItem for: {item['sold']}")
                EndOfDayItems.objects.create(
                    end_of_day=e_o_d,
                    dish_name=None if item['is_product'] else item['sold'],
                    finished_product=item['sold'] if item['is_product'] else None,
                    **update_kwargs
                )
            else:
                logger.info(f"Updating EndOfDayItem for: {item['sold']}")
                EndOfDayItems.objects.filter(end_of_day=e_o_d, dish_name=item['sold']).update(
                    **update_kwargs
                )
                

        eod_list = EndOfDayItems.objects.filter(end_of_day=e_o_d)
        
        for a in eod_list:
            print(a.dish_name, 'portions ->', a.total_portions, 'sold_', a.total_sold, 'staff_p', a.staff_portions, 'staff_wastage', a.wastage, 'leftovers', a.leftovers, a.expected, a.declared, a.servers_variance)

        return render(request, 'end_of_day.html', {
            'date': today,
            'production_today': eod_list,
        })
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            sold_name = data.get('sold')
            wastage = float(data.get('wastage', 0))
            leftovers = float(data.get('leftovers', 0))
            
            logger.info(data)

            today = datetime.date.today()
            branch = request.user.branch
            e_o_d, _ = EndOfDay.objects.get_or_create(date=today, branch=branch, done=False)

            eod_item = EndOfDayItems.objects.filter(end_of_day=e_o_d, dish_name=sold_name).first()
            
            if not eod_item:
                eod_item = EndOfDayItems.objects.create(
                    end_of_day=e_o_d,
                    dish_name=sold_name,
                    wastage=wastage,
                    leftovers=leftovers,
                    recorded=True
                )
            else:
                eod_item.wastage = wastage
                eod_item.leftovers = leftovers

            total_portions = eod_item.total_portions or 0
            staff_portions = eod_item.staff_portions or 0
            total_sold = eod_item.total_sold or 0
            declared = eod_item.declared or 0
            eod_item.recorded = True
            
            if declared:
                eod_item.servers_variance = declared - (total_sold + staff_portions + wastage + leftovers)
                logger.info(f'Variance: {eod_item.servers_variance}')

            
          
            eod_item.save()
            logger.success(f'End of Day item updated: {eod_item}')

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
@transaction.atomic
def confirm_end_of_day(request):
    try:
        today = localdate()
        branch = request.user.branch
        
        sales = Sale.objects.filter(date=today, staff=False, branch=branch).aggregate(total_amount=Sum('total_amount'))['total_amount'] or 0
        cashed_amount = request.POST.get('cashed_amount') or request.GET.get('cashed_amount')

        e_o_d = EndOfDay.objects.filter(date=today, branch=branch).first()
        e_o_d.total_sales = sales
        
        if cashed_amount:
            e_o_d.cashed_amount = cashed_amount
            
        e_o_d.done = True

        end_of_day_items = EndOfDayItems.objects.filter(end_of_day=e_o_d)
        products = Product.objects.filter(finished_product=True, branch=request.user.branch)
        purchase_order = PurchaseOrder.objects.filter(branch=request.user.branch, order_date__date=e_o_d.date, received=True).first()
        purchase_order_items = PurchaseOrderItem.objects.filter(purchase_order=purchase_order) 
        dishes = Dish.objects.filter()
        
        dishes_map = { dish.name: {'price': dish.price} for dish in dishes }
        variance = 0
        
        purchase_order_map = {}
        
        with transaction.atomic():
            
            for item in purchase_order_items:  # average cost to be revised 
                if item.product.name in purchase_order_map:
                    purchase_order_map[item.product.name] += item.quantity
                else:
                    purchase_order_map[item.product.name] = item.quantity

            products_map = {product.name: product for product in products}

            for eod_item in end_of_day_items:
                if eod_item.finished_product:
                    product = products_map.get(eod_item.finished_product)
                    purchase = purchase_order_map.get(eod_item.finished_product, 0)
                    if product:
                        eod_item.product_cost = product.cost * (eod_item.total_portions or 0)
                        eod_item.product_price = product.price * (eod_item.total_sold or 0)
                        eod_item.close_stock = product.quantity

                        if purchase:
                            eod_item.purchase_units = purchase

                        eod_item.open_stock = product.quantity + (eod_item.total_sold or 0) + (eod_item.staff_portions or 0) + purchase
                    else:
                        eod_item.product_cost = 0
                        eod_item.product_price = 0
                else:
                    eod_item.product_cost = 0
                    eod_item.product_price = 0
            
                dish = dishes_map.get(eod_item.dish_name)
                
                if dish and eod_item.servers_variance:
                    print(dish)
                    variance += Decimal(eod_item.servers_variance) * Decimal(dish['price'])
                
                eod_item.save()
                
            e_o_d.variance = variance
            e_o_d.save()
            
            logger.success(f'End of day successfully saved!')

        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f'Error, processing file: {e}')
        return JsonResponse({'success': False, 'message': f'invalid:{e}'})


@login_required
def supplier_prices(request, raw_material_name):
    """
        {
            raw_material_name: str
        }
    """
    try:
        
        best_three_prices = best_price(raw_material_name=raw_material_name, branch=request.user.branch)
        logger.info(best_three_prices)
        return JsonResponse({'success': True, 'suppliers': best_three_prices})

    except Exception as e:
        logger.error(f"Error fetching supplier prices: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def end_of_day_detail(request, e_o_d_id):
    download = request.GET.get('download', None)
    try:
        end_of_day = EndOfDay.objects.get(id=e_o_d_id, branch = request.user.branch)
        end_of_day_items = EndOfDayItems.objects.filter(end_of_day=end_of_day)
        dishes = Dish.objects.all()

        if download:
            context = {
                'end_of_day': end_of_day,
                'end_of_day_items': end_of_day_items,
                'dishes': dishes,
                'branch': request.user.branch,
            }
            return render_to_pdf(template_src="End_of_day_pdf_report.html", context_data=context)

        return render(request, 'end_of_day_detail.html', 
            {
                'dishes': dishes, 
                'end_of_day':end_of_day,
                'end_of_day_items':end_of_day_items,
            }
        )
    except Exception as e:
        logger.error(e)

@login_required
def undo_eod_record(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            eod_id = data.get('eod_id')
            EndOfDayItems.objects.filter(id=eod_id).update(declared=0, wastage=0, leftovers=0, expected=0, servers_variance=0, recorded=False)
            
            logger.success(f'End of Day record undone for ID: {eod_id}')
            
            return JsonResponse({'success': True, 'message': 'End of Day record undone successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
        
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)
    
def generate_end_of_day_report(end_of_day, items, staff_sold_amount):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    elements = []

    # Title
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'title_style',
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    title = Paragraph(f"End Of Day Report: {end_of_day.date}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Sales Section Title
    sales_title = Paragraph("Sales", styles['Heading2'])
    elements.append(sales_title)
    elements.append(Spacer(1, 6))

    # Sales Section
    sales_data = [
        ["Details", "Quantity", "Amount"],
        ["Total", "", f"{end_of_day.total_sales:.2f}"],
        ["Staff", "", "(6.00)"],
        ["Non Staff", "", f"{end_of_day.total_sales - 6:.2f}"],
        # ["Cashed Amount", "", f"{end_of_day.cashed_amount:.2f}"],
        # ["Difference", "", f"{end_of_day.cashed_amount - (end_of_day.total_sales - staff_sold_amount):.2f}"],
    ]

    sales_table = Table(sales_data, colWidths=[2 * inch, 1 * inch, 2 * inch])
    sales_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),  
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(sales_table)
    elements.append(Spacer(1, 12))

    # Dishes Section Title
    dishes_title = Paragraph("Dishes", styles['Heading2'])
    elements.append(dishes_title)
    elements.append(Spacer(1, 6))

    # Dishes Section
    dish_data = [
        ["Dish Name", "S A C Portions", "P Sold", "S Portions", "Price Per Unit", "Wastage", "Left Overs", "Over/Less"]
    ]
    for item in items:
        dish_data.append([
            item.dish_name,
            item.total_portions,
            item.total_sold,
            item.staff_portions,
            "N/A",  
            item.wastage,
            item.leftovers,
            item.expected
        ])

    dish_table = Table(dish_data, colWidths=[1 * inch] * 8)
    dish_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(dish_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# @login_required # put to tasks
def send_end_of_day_report(request, buffer):
    logger.info(f'Sending Email')
    email = EmailMessage(
        f"End of Day Report:",
        "Please find the attached End of Day report. The expected amount is to be calculated on cost price, since they are no stipulated prices per dishes, but if they to be put the expected table will be relavant.",
        'admin@techcity.co.zw',
        ['cassymyo@gmail.com', 'teddychinomona@gmail.com'],
    )
    email.attach(f'EndOfDayReport.pdf', buffer.getvalue(), 'application/pdf')
    
    EmailThread(email).start()

    logger.info(f' End of day report email sent.')
    

@login_required
def end_of_day_list(request):
    end_of_days = EndOfDay.objects.filter(done=True, branch = request.user.branch)
    logger.info(end_of_days)
    return render(request, 'end_of_day_list.html', {'eods':end_of_days})
 
@login_required 
def confirm_minor_raw(request):
    # payload 
    """
        {
            raw_material_id: float,
            quantity: float,
            production_id: int
        }
    """
    try:
        data = json.loads(request.body)
        logger.info(data)

        raw_material_id = data.get('raw_material_id')
        quantity = data.get('quantity')
        production_id = data.get('production_id')
        quantity = float(quantity)
        
        with transaction.atomic():
            raw_material = Product.objects.select_for_update().get(id=raw_material_id, branch = request.user.branch)
            production = Production.objects.get(id=production_id, branch = request.user.branch)
            production_plan_item = ProductionItems.objects.filter(production=production, )
            
            # check_list = CheckList.objects.get(product__id = raw_material_id, date = datetime.date.today())
            # check_list.product.quantity += quantity
            # check_list.save()

            # logger.info(check_list)

            p_raw_materials, created = ProductionRawMaterials.objects.get_or_create(
                product=raw_material,
                product__branch = request.user.branch,
                defaults={
                    "quantity": quantity,
                    "quantity_left": 0.0
                }  
            )

            logger.info({'BF': p_raw_materials.quantity})
            allocated_raw_materials = None
            try:
                allocated_raw_materials = AllocatedRawMaterials.objects.get(production=production,raw_material=raw_material)
            except Exception as e:
                logger.info(f'Not enter before: {e}')

            if allocated_raw_materials:
                allocated_raw_materials.quantity += quantity
            else:
                AllocatedRawMaterials.objects.create(
                    production=production,
                    raw_material=raw_material,
                    quantity=quantity
                )
            
            p_raw_materials.quantity += quantity
            p_raw_materials.save()
            
            #Temp to be changed using as check list example changed +
            raw_material.quantity += quantity


            raw_material.save()
            
            Logs.objects.create(
                user=request.user, 
                action='Transfer',
                description='to production',
                product=raw_material,
                quantity=quantity,
                total_quantity=raw_material.quantity,
            )
            
            ProductionLogs.objects.create(
                user=request.user, 
                action='stock in',
                description='from warehouse',
                product=p_raw_materials,
                quantity=quantity,
                total_quantity=p_raw_materials.quantity,
            )

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'{e}'}, status=400)
    return JsonResponse({'success': True}, status=200)

@login_required
def create_end_of_day_declaration(request):
    
    if request.method == 'GET':
        """
            products used,
            portions
        """
        inventory = Product.objects.filter(branch=request.user.branch).values('id', 'quantity', 'name')
        dishes = Dish.objects.filter(branch=request.user.branch).values('id', 'name')
        meals = Meal.objects.filter(branch=request.user.branch).values('id', 'name')
        
        meals_dishes = list(dishes) + list(meals)
        
        context = {
            'inventory':inventory,
            'dishes':dishes,
            'meals':meals
        }
        
        return render (request, 'end_of_declaration.html', context)

    if request.method == "POST":
        """
            [
                {
                    'dish_id': id,
                    'meal_id': id,
                    'quantity': int,
                }
            ]
        """
        try:
            data = json.loads(request.body)
            dish_id = data.get('dish_id', '')
            meal_id = data.get('meal_id', '')
            kgs = data.get('kgs')
            expected = data.get('expected')
            sold = data.get('sold')
            staff = data.get('staff')
            left_over = data.get('left_over')
            variance = data.get('variance')

        except Exception as e:
            logger.error(f'Error processing declare item: {e}')
    
    



@login_required
def calculate_reorder_point(product):
    average_weekly_usage = product.average_daily_usage * 7
    lead_time_in_weeks = product.lead_time / 7
    reorder_point = (average_weekly_usage * lead_time_in_weeks) + product.safety_stock
    return reorder_point


@login_required
def order_list(request):
    products = Product.objects.filter(branch = request.user.branch)
    six_days_ago = timezone.now() - timedelta(days=6)
    lead_time = 1 # 1 days to be put to settings
    
    for product in products:
        if product.min_stock_level >= product.quantity:
            logger.info(product)
            quantity_last_six_days = Logs.objects.filter(timestamp__gte=six_days_ago, product=product).aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 1
            
            reorder_quantity = quantity_last_six_days * lead_time + product.min_stock_level
            approx_days =  (product.quantity * 6) / reorder_quantity
            
            try:
                Reorder.objects.get_or_create(
                    product=product,
                    product__branch = request.user.branch,
                    defaults={
                        'ordered':False,
                        'approx_days':approx_days,
                        'reorder_quantity':reorder_quantity,
                    }
                )
            except Exception as e:
                logger.info(e)
                reorder_list = {}
            
    reorder_list = Reorder.objects.filter(product__branch = request.user.branch)
    
    return render(request, 'inventory/reorder.html', {'reorders':reorder_list})


@login_required
def transfers(request):
    trans = Transfer.objects.filter(branch = request.user.branch).order_by('-created_at')
    return render(request, 'inventory/transfers.html', {'transfers':trans})


@login_required
def production_transfers(request):
    trans = Transfer.objects.filter(branch = request.user.branch).order_by('-created_at')
    
    return render(request, 'inventory/production_transfers.html', {'transfers':trans})


@login_required
def transfer_to_production(request):
    if request.method == 'GET':
        form = TransferForm()
        products = Product.objects.filter(branch = request.user.branch)
        return render(request, 'inventory/add_transfer.html', {'form':form, 'products':products})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('cart')
            
            with transaction.atomic():
                transfer = Transfer.objects.create(status=False, branch = request.user.branch)
                
                for item in items:
                    product_id = item['product_id']
                    quantity = float(item['quantity'])
                    logger.info(f'Processing quantity: {quantity}')
                    
                    product = Product.objects.get(id=product_id, branch= request.user.branch)
                    
                    TransferItems.objects.create(
                        transfer=transfer,
                        product=product,
                        quantity=quantity
                    )
                    
                    product.quantity -= quantity
                    product.save()
                    
                    logger.info(f'Updated product quantity: {product.quantity}')
                
                # send notification email
                transfer_notification(transfer.id)
                
            return JsonResponse({'success': True}, status=201)
        except Exception as e:
            transaction.rollback()
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@login_required
def accept_transfer(request, transfer_id):
    try:
        with transaction.atomic():

            transfer = Transfer.objects.get(id=transfer_id, branch = request.user.branch)
            transfer_items = TransferItems.objects.filter(transfer=transfer)

            for item in transfer_items:
                product, created = ProductionRawMaterials.objects.get_or_create(
                    product=item.product,
                    product__branch = request.user.branch,
                    defaults={
                        'quantity': item.quantity
                    }
                )
                
                if not created:
                    product.quantity += item.quantity
                    product.save()

            transfer.status = True
            transfer.save()  

            messages.success(request, f'{transfer.transfer_number} successfully received')
            return redirect('inventory:production_transfers')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
        return redirect('inventory:receive_transfer_detail', transfer_id)
 
        
@login_required
def receive_transfers_detail(request, transfer_id):
    try:
        transfer = Transfer.objects.get(id=transfer_id, branch = request.user.branch)
        transfer_items = TransferItems.objects.filter(transfer=transfer)
        logger.info('one')
        return render(request, 'inventory/receive_transfer_detail.html', 
            {
                'transfer':transfer,
                'transfer_items':transfer_items
            }
        )
    except Exception as e:
        messages.warning(request, f'{e}')
        return redirect('inventory:production_transfers')
 
    
@login_required
def production_sales(request):
    filter_option = request.GET.get('filter', 'today')
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

    if filter_option == 'custom':
        production_data = ProductionItems.objects.filter(
            production__date_created__range=[start_date, end_date], production__branch = request.user.branch
        ).values(
            'dish__name'
        ).annotate(
            total_wastage = Sum('wastage'),
            total_cost = Sum('total_cost'),
            total_portions=Sum('portions'),
            total_sold=Sum('portions_sold'),
            total_left_overs = Sum('left_overs')
        ).order_by('dish__name')
    else:
        production_data = ProductionItems.objects.filter(
            production__date_created__gte=start_date, production__branch = request.user.branch
        ).values(
            'dish__name'
        ).annotate(
            total_wastage = Sum('wastage'),
            total_cost = Sum('total_cost'),
            total_portions=Sum('portions'),
            total_sold=Sum('portions_sold'),
            total_left_overs = Sum('left_overs')
        ).order_by('dish__name')
        

    if request.GET.get('download') == 'csv':
        # Generate CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="production_sales_{filter_option}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Dish Name', 'Total Portions', 'Total Sold Portions'])

        for item in production_data:
            writer.writerow([item['dish__name'], item['total_portions'], item['total_sold']])

        return response

    return render(request, 'inventory/production_sales.html', {'production_data': production_data, 'filter_by': filter_option})

@login_required
def check_check_list(request):
    # Payload 
    """
    {
        "check_list_id": id
    }
    """
    try:
        data = json.loads(request.body)
        check_list_id = data.get('check_list_id')
        
        if not check_list_id:
            return JsonResponse({'success': False, 'message': 'Missing check_list_id'}, status=400)
        
        check_list_item = get_object_or_404(CheckList, id=check_list_id, product__branch = request.user.branch)
        
        check_list_item.status = not check_list_item.status
        
        check_list_item.save(update_fields=['status'])
        
        return JsonResponse({'success': True, 'message': 'Checklist status updated'}, status=200)
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
def chef_checklist(request):
    """Chef-specific checklist view"""
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch=request.user.branch)
    non_production_products = Product.objects.filter(raw_material=False, branch=request.user.branch)
    
    check_list = []
    for product in non_production_products:
        if not products.filter(product=product).exists():
            check_list.append(CheckList(
                product=product,
                status=False
            ))
    
    CheckList.objects.bulk_create(check_list)
    
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch=request.user.branch)
    
    return render(request, 'inventory/checklist_chef.html', {'products': products})

@login_required
def check_list_finished_products(request):
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch = request.user.branch)
    non_production_products = ProductionRawMaterials.objects.filter(product__raw_material=False, product__branch = request.user.branch)

    check_list = []
    for product in non_production_products:
        if not products.filter(product=product.product).exists():
            check_list.append(CheckList(
                product = product.product,
                status = False
            ))

    CheckList.objects.bulk_create(check_list)
    
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__raw_material=False, product__branch = request.user.branch)

    return JsonResponse({'success': True, 'products': list(products.values('product__name', 'product__quantity', 'status', 'product__id'))}, status=200)


@login_required
def check_list_raw_products(request):
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch = request.user.branch)
    non_production_products = ProductionRawMaterials.objects.filter(product__raw_material=True, product__branch = request.user.branch)

    check_list = []
    for product in non_production_products:
        if not products.filter(product=product.product).exists():
            check_list.append(CheckList(
                product = product.product,
                status = False
            ))

    CheckList.objects.bulk_create(check_list)
    
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__raw_material=True, product__branch = request.user.branch)

    return JsonResponse({'success': True, 'products': list(products.values('product__name', 'product__quantity', 'status', 'product__id'))}, status=200)

@login_required
def check_list_all_products(request):
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch = request.user.branch)
    non_production_products = ProductionRawMaterials.objects.filter(product__branch = request.user.branch)
    
    check_list = []
    for product in non_production_products:
        if not products.filter(product=product.product).exists():
            check_list.append(CheckList(
                product = product.product,
                status = False
            ))

    CheckList.objects.bulk_create(check_list)
    
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch = request.user.branch)

    return JsonResponse({'success': True, 'products': list(products.values('product__name', 'product__quantity', 'status', 'product__id'))}, status=200)

@login_required
def budget(request):
    if request.method == 'GET':
        budgets = Budget.objects.all().select_related('user')
        reodre = Reorder.objects.filter(product__branch = request.user.branch)
        exp = Expense.objects.all()
        logger.info(reodre)
        logger.info(exp)
        reorder_list = []
        expense_list = []
        for item in reodre:
            reorder_list.append({
                'name': item.product.name,
                'amount': item.product.cost,
                'quantity': item.reorder_quantity
            })
        for item in exp:
            expense_list.append({
                'name': item.category.name,
                'amount': item.amount,
            })
        
        logger.info(expense_list + reorder_list)
        combined_list = expense_list + reorder_list
        return render(request, 'inventory/budgets/budget.html', {
            'budgets':budgets,
            'combined': combined_list,
        })
    elif request.method == 'DELETE':
        data = json.loads(request.body)
        b_id = data.get('id')
        logger.info(b_id)
        try:
            with transaction.atomic():
                budget_item_delete = BudgetItem.objects.get(budget__id = b_id)
                budget_delete = Budget.objects.get(id = b_id)
                budget_item_delete.delete()
                budget_delete.delete()
                return JsonResponse({'success': True}, status = 200)
        except Exception as e:
            return JsonResponse({'success': False, 'message':f'{e}'}, status = 400)
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            id = data.get('id')

            budget_infomation = BudgetItem.objects.filter(budget__id = id).select_related('budget', 'product')
           
            budget_list = []
            for item in budget_infomation:
                budget_list.append(
                    {
                        'budget_name': item.budget.name,
                        'budget_cost': item.budget.total_amount,
                        'product': item.product.name,
                        'quantity': item.quantity,
                        'amount': item.allocated_amount,
                        'spent': item.spent_amount
                    }
                )
            logger.info(budget_list)
            return JsonResponse({'success': True,'budget': budget_list}, status = 200)
        except Exception as e:
            return JsonResponse({'success': False, 'message':f'Error encountered is:{e}'}, status = 400)
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            id = data.get('id')

            budget_infomation = BudgetItem.objects.filter(budget__id = id).select_related('budget', 'product')
           
            budget_list = []
            for item in budget_infomation:
                budget_list.append(
                    {
                        'budget_name': item.budget.name,
                        'budget_cost': item.budget.total_amount,
                        'product': item.product.name,
                        'quantity': item.quantity,
                        'amount': item.allocated_amount,
                        'spent': item.spent_amount
                    }
                )
            logger.info(budget_list)
            return JsonResponse({'success': True,'budget': budget_list}, status = 200)
        except Exception as e:
            return JsonResponse({'success': False, 'message':f'Error encountered is:{e}'}, status = 400)

@login_required
def createBudgetItem(request):
    if request.method == 'GET':
        form = CreateBudgetItemForm()
        reodre = Reorder.objects.filter(product__branch = request.user.branch)
        exp = Expense.objects.all()
    
        reorder_list = []
        expense_list = []
        for item in reodre:
            reorder_list.append({
                'id': item.id,
                'name': item.product.name,
                'amount': item.product.price,
                'quantity': item.reorder_quantity
            })
        for item in exp:
            expense_list.append({
                'id': item.id,
                'name': item.category.name,
                'amount': item.amount,
            })
        
        logger.info(expense_list + reorder_list)
        combined_list = expense_list + reorder_list
        
        return render(request, 'inventory/budgets/create_budget.html', {
            'form':form,
            'combined': combined_list,
        })
    
    if request.method == 'POST':
        data = json.loads(request.body)
        
        with transaction.atomic():
            items_info = data.get('cart')
            logger.info(items_info)
            
            budget_total_cost = 0

            for item in items_info:
                budget_total_cost += item['total_cost']

            budget_info = Budget.objects.create(
                name = 'BugetTest',
                total_amount = budget_total_cost,
                description = '',
                start_date = '2025-01-09',
                end_date = '2025-01-09',
                confirmation =  False,
                user = request.user
            )
            
            budget_items = []

            # Loop through the items_info and create BudgetItem instances
            for item in items_info:
                prod_info = Product.objects.get(id=item['product']) 
                
                budget_items.append(
                    BudgetItem(
                        budget=budget_info,
                        product=prod_info,
                        quantity=item['quantity'],
                        allocated_amount=item['total_cost'],
                        spent_amount=0.00,
                    )
                )
                BudgetItem.objects.bulk_create(budget_items)
            return JsonResponse({'success':True}, status= 201)

def ViewBudget(request, id):
    if request.method == 'GET':
        try:
            budget_info = BudgetItem.objects.filter(budget__id = id).select_related('product', 'budget')
            logger.info(budget_info)
            budget_info_list = []
            for item in budget_info:
                budget_info_list.append(
                    {
                        'product': item.product.name,
                        'Quantity': item.quantity,
                        'Amount': item.allocated_amount,
                        'Spent amount': item.spent_amount
                    }
                )
            return JsonResponse({'success': True, 'data':budget_info_list}, status = 200)
        except Exception as e:
            return JsonResponse({'success': False, 'message':e}, status = 400)

@login_required
def BudgetApproval(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        if data.get('Save') == 'all':

            budget_item_list = []
            for item in data.get('budget_info'):
                budget_item = BudgetItem.objects.get(id = data.get('budget_item_id'))
                budget_item.spent_amount = item.get('approoved_amount')
                budget_item_list.append(budget_item)
            BudgetItem.objects.bulk_update(budget_item_list, ['spent_amount'])
            return JsonResponse({'success': True}, status = 201)
        else:
            budget_item_info = BudgetItem.objects.get(id = data.get('budget_item_id'))

            budget_item_info.spent_amount = float(data.get('approoved_amount'))
            budget_item_info.save()
            return JsonResponse({'success': True}, status = 201)
    return JsonResponse({'success': False}, status = 500)

@login_required
def ConversionFormula(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        logger.info(data.get('period'))

        purchase_info = PurchaseOrderItem.objects.all()
        product_info = Product.objects.all()

        inventory_list = []
        inventory_total = 0
        for item in purchase_info:
            id = item.product.id
            for items in product_info:
                if id == items.id:
                    inventory_list.append({
                        'name': items.name,
                        'date': item.purchase_order.order_date,
                        'cost': item.unit_cost,
                        'quantity': item.quantity
                    })
                    inventory_total += (item.unit_cost * Decimal(item.quantity))


        reorder_info = Reorder.objects.filter(ordered = False, product__branch = request.user.branch)
        for item in reorder_info:
            name = item.product.name
            for items in inventory_list:
                if name == items['name']:
                    new_date = items['date'] + timedelta(days=item.approx_days)
                    items['reorder_date'] = new_date


        expense_info = Expense.objects.all()
        expense_list = []
        expense_total = 0
    
        for item in expense_info:
            expense_total += item.amount
            expense_list.append({
                'category': item.category.name,
                'date': item.date,
                'amount': item.amount
            })

        grouped_expenses = {}
        for item in expense_info:
            category = item.category.name
            amount = item.amount
            
            if category in grouped_expenses:
                grouped_expenses[category] += amount
            else:
                grouped_expenses[category] = amount
        logger.info(grouped_expenses)

        previous = None
        count = 0
        date_diff = 0
        sum_diff = timedelta(days=0)
        id_in_use = 0
        for items in expense_info:
            count += 1
            id = items.category.id
            if previous is not None and id == id_in_use:
                date_diff = items.date - previous
                sum_diff += date_diff
                logger.info('inside')
            previous = items.date
            id_in_use = item.category.id
            logger.info(date_diff)
            logger.info(previous)
            logger.info(count)

        if data.get('period') == 'daily':
            time_diff = 0
            for item in inventory_list:
                first_date = item['date']
                last_date = item['reorder_date']
                time_diff = first_date - last_date
                logger.info(time_diff)
                time_diff_in_days = abs(time_diff.total_seconds() / 86400)
                logger.info(time_diff_in_days)
                estimate_quantity = (1/time_diff_in_days) * item['quantity']
                estimate_cost = Decimal(estimate_quantity) * item['cost']
                rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                logger.info(estimate_quantity)
                logger.info(rounded_estimate_cost)
                item['estimated_quantity'] = estimate_quantity
                item['estimated_cost'] = rounded_estimate_cost
        elif data.get('period') =='weekly':
            time_diff = 0
            for item in inventory_list:
                first_date = item['date']
                last_date = item['reorder_date']
                time_diff = first_date - last_date
                logger.info(time_diff)
                time_diff_in_days = abs(time_diff.total_seconds() / 86400)
                if time_diff_in_days <= 7:
                    estimate_quantity = (7/time_diff_in_days) * item['quantity']
                    estimate_cost = Decimal(estimate_quantity) * item['cost']
                    rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                    logger.info(estimate_quantity)
                    logger.info(rounded_estimate_cost)
                    item['estimated_quantity'] = estimate_quantity
                    item['estimated_cost'] = rounded_estimate_cost
                if time_diff_in_days >= 7:
                    estimate_quantity = (time_diff_in_days/7) * item['quantity']
                    estimate_cost = Decimal(estimate_quantity) * item['cost']
                    rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                    logger.info(estimate_quantity)
                    logger.info(rounded_estimate_cost)
                    item['estimated_quantity'] = estimate_quantity
                    item['estimated_cost'] = rounded_estimate_cost
        elif data.get('period') =='monthly':
            time_diff = 0
            for item in inventory_list:
                first_date = item['date']
                last_date = item['reorder_date']
                time_diff = first_date - last_date
                logger.info(time_diff)
                time_diff_in_days = abs(time_diff.total_seconds() / 86400)
                if time_diff_in_days <= 31:
                    estimate_quantity = (31/time_diff_in_days) * item['quantity']
                    estimate_cost = Decimal(estimate_quantity) * item['cost']
                    rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                    logger.info(estimate_quantity)
                    logger.info(rounded_estimate_cost)
                    item['estimated_quantity'] = estimate_quantity
                    item['estimated_cost'] = rounded_estimate_cost
                if time_diff_in_days >= 31:
                    estimate_quantity = (time_diff_in_days/31) * item['quantity']
                    estimate_cost = Decimal(estimate_quantity) * item['cost']
                    rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                    logger.info(estimate_quantity)
                    logger.info(rounded_estimate_cost)
                    item['estimated_quantity'] = estimate_quantity
                    item['estimated_cost'] = rounded_estimate_cost
        elif data.get('period') =='yearly':
            time_diff = 0
            for item in inventory_list:
                first_date = item['date']
                last_date = item['reorder_date']
                time_diff = first_date - last_date
                logger.info(time_diff)
                time_diff_in_days = abs(time_diff.total_seconds() / 86400)
                if time_diff_in_days <= 356:
                    estimate_quantity = (356/time_diff_in_days) * item['quantity']
                    estimate_cost = Decimal(estimate_quantity) * item['cost']
                    rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                    logger.info(estimate_quantity)
                    logger.info(rounded_estimate_cost)
                    item['estimated_quantity'] = estimate_quantity
                    item['estimated_cost'] = rounded_estimate_cost
                if time_diff_in_days >= 356:
                    estimate_quantity = (time_diff_in_days/356) * item['quantity']
                    estimate_cost = Decimal(estimate_quantity) * item['cost']
                    rounded_estimate_cost = estimate_cost.quantize(Decimal('0.01'),  rounding=ROUND_HALF_UP)
                    logger.info(estimate_quantity)
                    logger.info(rounded_estimate_cost)
                    item['estimated_quantity'] = estimate_quantity
                    item['estimated_cost'] = rounded_estimate_cost

        combined_list = [
            {'Inventory':
                { 
                'inventory_details': inventory_list,
                'total': inventory_total
                }
            }, 
            {'Expenses': 
                {
                    'expanse_details':[grouped_expenses],
                    'total': expense_total
                }
            }
        ]
        logger.info(combined_list)
        return JsonResponse({'success': True,'combined_list': combined_list}, status = 200)




@login_required
# @admin_required
def shift_data_to_main(request):
    from finance.models import CashierExpense, transactionLog

    company = Company.objects.all().first()
    print(f'Company :{company.name}')
    with transaction.atomic():
        branch_data = Branch.objects.filter(branch_name__icontains = 'Main').first()
        if not branch_data:
            Branch.objects.create(
                branch_name = 'Main',
                company = company
            )
        branch = Branch.objects.filter(branch_name__icontains = 'Main').first()

        user_data = User.objects.update(branch = branch)
        # for user in user_data:
        #     user.branch = branch

        # User.objects.abulk_update(user_data, ['branch'])

        supplier_data = Supplier.objects.update(branch = branch)

        product_data = Product.objects.update(branch = branch)

        production_data = Production.objects.update(branch = branch)

        dish_data = Dish.objects.update(branch = branch)

        meal_data = Meal.objects.update(branch = branch)

        purchase_order_data = PurchaseOrder.objects.update(branch = branch)

        endofday_data = EndOfDay.objects.update(branch = branch)

        sale_data = Sale.objects.update(branch = branch)

        cashbook_data = CashBook.objects.update(branch = branch)

        cashup_data = CashUp.objects.update(branch = branch)

        cashier_expense_data = CashierExpense.objects.update(branch = branch)

        transactionlogs_data = transactionLog.objects.update(branch = branch)

        transfer_data = Transfer.objects.update(branch = branch)

        production_logs_data = ProductionLogs.objects.update(branch = branch)

        end_of_day_stock_data = EndOfDayStock.objects.update(branch = branch)

        expense_data = Expense.objects.update(branch = branch)
        
        return JsonResponse(
            {
                'success': True,
                'data': {
                    'supplier_data': supplier_data,
                    'product_data': product_data,
                    'production_data': production_data,
                    'dish_data': dish_data,
                    'meal_data': meal_data,
                    'purchase_order_data': purchase_order_data,
                    'endofday_data': endofday_data,
                    'sale_data': sale_data,
                    'cashbook_data': cashbook_data,
                    'cashup_data': cashup_data,
                    'cashier_expense_data': cashier_expense_data,
                    'transactionlogs_data': transactionlogs_data,
                    'transfer_data': transfer_data,
                    'production_logs_data': production_logs_data,
                    'end_of_day_stock_data': end_of_day_stock_data,
                    'expense_data': expense_data  
                } 
            }, status = 200
        )

@login_required   
def production_plans_ajax(request):
    """AJAX version of production_plans that returns only the content"""
    from datetime import datetime, timedelta
    selected_date = request.GET.get('date', datetime.now().strftime('%Y-%m-%d'))
    date_filter = None
    try:
        if selected_date == 'yesterday': 
            filter_date = datetime.now().date() - timedelta(days=1)
        elif selected_date == 'today': 
            filter_date = datetime.now().date()
        elif selected_date == 'week':
            today = datetime.now().date()
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            filter_date = week_start
            date_filter = 'week'
        else: 
            filter_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except: 
        filter_date = datetime.now().date()
    
    if date_filter == 'week':
        plans = Production.objects.filter(branch=request.user.branch, date_created__range=[week_start, week_end]).order_by('date_created')
    else:
        plans = Production.objects.filter(branch=request.user.branch, date_created=filter_date).order_by('date_created') 
    
    transfer_count = Transfer.objects.filter(status=False, branch=request.user.branch).count()
    products = Product.objects.filter(branch=request.user.branch).order_by('name')[:15]
    
    # For stores person, get plans that are confirmed but not declared
    if request.user.role == 'stores_person':
        declaration_plans = Production.objects.filter(
            branch=request.user.branch,
            status=True,  # Confirmed by chef
            declared=False  # Not yet declared by stores person
        ).order_by('date_created')
    else:
        declaration_plans = plans
        
    context = { 
        'plans': plans, 
        'declaration_plans': declaration_plans,
        'transfer_count': transfer_count, 
        'products': products, 
        'selected_date': filter_date, 
        'today': datetime.now().date(), 
        'yesterday': datetime.now().date() - timedelta(days=1), 
        'date_filter': date_filter 
    }
    if date_filter == 'week': 
        context.update({'week_start': week_start, 'week_end': week_end})
    
    # Return different templates based on user role
    if request.user.role == 'stores_person':
        return render(request, 'inventory/production_plans_declaration_content.html', context)
    else:
        return render(request, 'inventory/production_plans_content.html', context)


@chef_or_stores_view_required
def production_declaration_table_ajax(request):
    """AJAX view for production plan declaration table - simplified version"""
    # Debug logging
    logger.info(f"User: {request.user.username}, Role: {request.user.role}, Branch: {request.user.branch}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request path: {request.path}")
    logger.info(f"User authenticated: {request.user.is_authenticated}")
    
    plans = Production.objects.filter(
        branch=request.user.branch
    ).order_by('-date_created', '-time_created')
    
    logger.info(f"Found {plans.count()} production plans for branch {request.user.branch}")
   
    for plan in plans:
        plan_items = ProductionItems.objects.filter(production=plan)

        planned_amount = sum(item.portions or 0 for item in plan_items)
        plan.planned_amount = planned_amount

        actual_production_amount = sum(item.actual_quantity or 0 for item in plan_items)
        plan.actual_production_amount = actual_production_amount
        
        production_cost = sum(item.total_cost or 0 for item in plan_items)
        plan.production_cost = production_cost

        variance = actual_production_amount - planned_amount
        plan.variance = variance

        if variance > 0:
            plan.positive_variance = variance
            plan.negative_variance = 0
        elif variance < 0:
            plan.positive_variance = 0
            plan.negative_variance = abs(variance)  
        else:
            plan.positive_variance = 0
            plan.negative_variance = 0
        
    context = {
        'plans': plans,
    }
    
    return render(request, 'inventory/production_declaration_table.html', context)

@login_required
def production_plan_detail_ajax(request, plan_id):
    """AJAX view for detailed production plan information"""
    import traceback
    from django.template.loader import render_to_string
    
    try:
        logger.info(f"Starting production_plan_detail_ajax for plan_id: {plan_id}")
        
        # Check if request is AJAX
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
        
        # Get the specific production plan
        try:
            plan = Production.objects.get(id=plan_id, branch=request.user.branch)
            logger.info(f"Found production plan: {plan.id}")
        except Production.DoesNotExist:
            logger.error(f"Production plan not found: {plan_id}")
            return JsonResponse({'success': False, 'error': 'Production plan not found'}, status=404)
        except Exception as e:
            logger.error(f"Error getting production plan: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False, 
                'error': 'Error retrieving production plan details',
                'debug': str(e) if request.user.is_staff else None
            }, status=500)
        
        # Get production items for this plan
        try:
            plan_items = list(ProductionItems.objects.filter(production=plan).select_related('dish'))
            if not plan_items:
                return JsonResponse({
                    'success': False,
                    'error': 'No production items found for this plan',
                    'html': render_to_string('inventory/production_plan_detail_dropdown.html', {
                        'error': 'No production items found for this plan',
                        'is_staff': request.user.is_staff
                    })
                })
            logger.info(f"Found {len(plan_items)} plan items")
        except Exception as e:
            logger.error(f"Error getting plan items: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False, 
                'error': 'Error retrieving plan items',
                'debug': str(e) if request.user.is_staff else None
            }, status=500)
        
        # Get dish ingredients for display
        try:
            dish_ingredients = list(Ingredient.objects.filter(
                minor_raw_material__branch=request.user.branch
            ).select_related('minor_raw_material', 'dish'))
            logger.info(f"Found {len(dish_ingredients)} dish ingredients")
        except Exception as e:
            logger.error(f"Error getting dish ingredients: {str(e)}\n{traceback.format_exc()}")
            # Don't fail the whole request if we can't get ingredients
            dish_ingredients = []
            
        # Dictionary to consolidate ingredients by name
        consolidated_ingredients = {}
        
        # Get ingredients/raw materials for this plan with detailed information
        ingredients = []
        raw_materials = []
        raw_materials_map = {}  # To track raw materials by ID
        
        try:
            for item in plan_items:
                if not hasattr(item, 'dish') or not item.dish:
                    logger.warning(f"Plan item {item.id} has no dish associated")
                    continue
                    
                logger.info(f"Processing plan item {item.id} for dish: {item.dish.name if item.dish else 'None'}")
                
                # Get ingredients for this dish
                try:
                    dish_ingredients_for_item = list(Ingredient.objects.filter(
                        dish=item.dish, 
                        minor_raw_material__branch=request.user.branch,
                        minor_raw_material__isnull=False  # Only include ingredients with valid raw materials
                    ).select_related('minor_raw_material', 'minor_raw_material__unit'))
                    
                    # Skip if no valid ingredients found
                    if not dish_ingredients_for_item:
                        logger.warning(f"No valid ingredients found for dish {item.dish.id} - {item.dish.name}")
                        continue
                        
                    logger.info(f"Found {len(dish_ingredients_for_item)} ingredients for dish {item.dish.id}")
                except Exception as e:
                    logger.error(f"Error getting ingredients for dish {item.dish.id}: {str(e)}\n{traceback.format_exc()}")
                    continue
                
                for ing in dish_ingredients_for_item:
                    try:
                        if not hasattr(ing, 'minor_raw_material') or not ing.minor_raw_material:
                            logger.warning(f"Ingredient {ing.id} has no minor_raw_material")
                            continue
                            
                        if not hasattr(ing.minor_raw_material, 'unit'):
                            logger.warning(f"Minor raw material {ing.minor_raw_material.id} has no unit")
                            continue
                        
                        # Skip if any required attributes are missing
                        if not all([hasattr(ing, 'minor_raw_material'), 
                                 hasattr(ing.minor_raw_material, 'unit'),
                                 hasattr(ing, 'quantity'),
                                 hasattr(item, 'portions'),
                                 hasattr(item, 'dish')]):
                            logger.warning(f"Skipping ingredient {getattr(ing, 'id', 'unknown')} due to missing required attributes")
                            continue
                            
                        # Calculate quantities - convert to Decimal for consistent calculations
                        try:
                            ing_quantity = Decimal(str(ing.quantity)) if ing.quantity is not None else Decimal('0')
                            item_portions = Decimal(str(item.portions)) if item.portions is not None else Decimal('0')
                            portion_multiplier = Decimal(str(item.dish.portion_multiplier)) if hasattr(item.dish, 'portion_multiplier') and item.dish.portion_multiplier is not None else Decimal('1')
                        except (TypeError, ValueError, InvalidOperation) as e:
                            logger.error(f"Error converting quantities to Decimal: {str(e)}\nIngredient: {ing.id}, Dish: {item.dish.id if item.dish else 'None'}")
                            continue
                            
                        if portion_multiplier == 0:
                            logger.warning(f"Portion multiplier is 0 for dish {item.dish.id}, using 1 to avoid division by zero")
                            portion_multiplier = Decimal('1')
                        
                        required_quantity = float(ing_quantity * (item_portions / portion_multiplier))
                        
                        # Get production raw materials info
                        try:
                            production_inventory = ProductionRawMaterials.objects.filter(
                                product=ing.minor_raw_material, 
                                product__branch=request.user.branch
                            ).first()
                            current_quantity = float(production_inventory.quantity) if production_inventory and production_inventory.quantity is not None else 0.0
                        except Exception as e:
                            logger.error(f"Error getting production inventory: {str(e)}")
                            current_quantity = 0.0
                            
                        expected_quantity = required_quantity - current_quantity
                        
                        # Get override history
                        try:
                            overrided_raw_materials = list(OverrideHistory.objects.filter(
                                raw_material_overrided=ing.minor_raw_material, 
                                raw_material_overrided__branch=request.user.branch
                            ))
                            total_overrides_up = sum(float(item.up) if item.up is not None else 0 for item in overrided_raw_materials)
                            total_overrides_down = sum(float(item.down) if item.down is not None else 0 for item in overrided_raw_materials)
                        except Exception as e:
                            logger.error(f"Error getting override history: {str(e)}")
                            total_overrides_up = 0
                            total_overrides_down = 0
                        
                        # Check if raw material already exists in the list
                        raw_material_found = raw_materials_map.get(ing.minor_raw_material.id)
                        
                        if raw_material_found:
                            raw_material_found['quantity'] += required_quantity
                            raw_material_found['expected_quantity'] += expected_quantity
                            raw_material_found['quantity_b_f'] += current_quantity
                            
                            # Update dollar amounts
                            cost_per_unit = float(ing.minor_raw_material.cost or 0)
                            raw_material_found['planned_amount'] = raw_material_found['quantity'] * cost_per_unit
                            raw_material_found['expected_amount'] = raw_material_found['quantity'] * cost_per_unit
                            raw_material_found['declared_amount'] = raw_material_found['expected_quantity'] * cost_per_unit if plan.declared else 0
                            raw_material_found['actual_amount'] = raw_material_found['expected_quantity'] * cost_per_unit if plan.declared else 0
                            raw_material_found['variance_amount'] = (raw_material_found['expected_quantity'] - raw_material_found['quantity']) * cost_per_unit if plan.declared else 0
                        else:
                            cost_per_unit = float(ing.minor_raw_material.cost or 0)
                            total_cost = required_quantity * cost_per_unit
                            
                            # Calculate dollar amounts
                            planned_amount = required_quantity * cost_per_unit
                            expected_amount = required_quantity * cost_per_unit
                            declared_amount = expected_quantity * cost_per_unit if getattr(plan, 'declared', False) else 0
                            actual_amount = expected_quantity * cost_per_unit if getattr(plan, 'declared', False) else 0
                            variance_amount = (expected_quantity - required_quantity) * cost_per_unit if getattr(plan, 'declared', False) else 0
                            
                            raw_material_data = {
                                'id': ing.minor_raw_material.id,
                                'name': ing.minor_raw_material.name,
                                'quantity_b_f': float(current_quantity),
                                'quantity': float(required_quantity),
                                'expected_quantity': float(expected_quantity),
                                'accumulated_overrides_up': total_overrides_up,
                                'accumulated_overrides_down': total_overrides_down,
                                'unit': ing.minor_raw_material.unit.unit_name if hasattr(ing.minor_raw_material.unit, 'unit_name') else 'unit',
                                'cost_per_unit': cost_per_unit,
                                'total_cost': total_cost,
                                'planned_amount': planned_amount,
                                'expected_amount': expected_amount,
                                'declared_amount': declared_amount,
                                'actual_amount': actual_amount,
                                'variance_amount': variance_amount,
                            }
                            
                            raw_materials.append(raw_material_data)
                            raw_materials_map[ing.minor_raw_material.id] = raw_material_data
                        
                        # Add to ingredients list for basic info
                        try:
                            stock_available = float(ing.minor_raw_material.quantity) if ing.minor_raw_material.quantity is not None else 0.0
                            stock_status = 'Sufficient' if stock_available >= required_quantity else 'Insufficient'
                            cost_per_unit = float(ing.minor_raw_material.cost or 0)
                            total_cost = required_quantity * cost_per_unit
                            
                            # Add or update ingredient in consolidated dictionary
                            ingredient_name = ing.minor_raw_material.name
                            unit_name = ing.minor_raw_material.unit.unit_name if hasattr(ing.minor_raw_material.unit, 'unit_name') else 'unit'
                            
                            if ingredient_name in consolidated_ingredients:
                                # Update existing ingredient
                                existing = consolidated_ingredients[ingredient_name]
                                existing['quantity_required'] += required_quantity
                                existing['total_cost'] += total_cost
                                existing['stock_available'] += stock_available
                                # Update status based on new totals
                                existing['stock_status'] = 'Sufficient' if existing['stock_available'] >= existing['quantity_required'] else 'Insufficient'
                            else:
                                # Add new ingredient
                                consolidated_ingredients[ingredient_name] = {
                                    'product_id': getattr(ing.minor_raw_material, 'id', None),
                                    'name': ingredient_name,
                                    'quantity_required': required_quantity,
                                    'unit': unit_name,
                                    'cost_per_unit': cost_per_unit,
                                    'total_cost': total_cost,
                                    'stock_available': stock_available,
                                    'stock_status': 'Sufficient' if stock_available >= required_quantity else 'Insufficient',
                                    'allocated_quantity': 0,  # Will be updated from raw_materials
                                    'declared_quantity': 0,   # Will be updated from raw_materials
                                    'variance_amount': 0      # Will be updated from raw_materials
                                }
                        except Exception as e:
                            logger.error(f"Error adding to ingredients list: {str(e)}")
                            
                    except Exception as ing_error:
                        logger.error(f"Error processing ingredient {getattr(ing, 'id', 'unknown')}: {str(ing_error)}\n{traceback.format_exc()}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error processing plan items: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'error': 'Error processing plan items',
                'details': str(e)
            }, status=500)
        
        try:
            # Calculate totals and add cost per portion to plan items
            total_planned_portions = 0
            total_actual_portions = 0
            total_production_cost = 0
            total_ingredients_cost = 0
            
            # Ensure we have valid numeric values for all calculations
            try:
                total_planned_portions = sum(float(item.portions) if item.portions is not None else 0 for item in plan_items)
                total_actual_portions = sum(float(item.actual_quantity) if item.actual_quantity is not None else 0 for item in plan_items)
                total_production_cost = sum(float(item.total_cost) if item.total_cost is not None else 0 for item in plan_items)
                total_ingredients_cost = sum(float(ing.get('total_cost', 0)) for ing in ingredients)
            except (TypeError, ValueError) as e:
                logger.error(f"Error calculating totals: {str(e)}\n{traceback.format_exc()}")
                # Continue with defaults if calculation fails
                total_planned_portions = 0
                total_actual_portions = 0
                total_production_cost = 0
                total_ingredients_cost = 0
            
            # Add cost per portion to plan items
            for item in plan_items:
                try:
                    if hasattr(item, 'portions') and item.portions and float(item.portions) > 0:
                        total_cost = float(item.total_cost) if hasattr(item, 'total_cost') and item.total_cost is not None else 0
                        portions = float(item.portions)
                        item.cost_per_portion = total_cost / portions if portions > 0 else 0
                    else:
                        item.cost_per_portion = 0
                except (TypeError, ValueError, ZeroDivisionError) as e:
                    logger.error(f"Error calculating cost per portion for item {getattr(item, 'id', 'unknown')}: {str(e)}")
                    item.cost_per_portion = 0
            
            # Calculate variance with safe type conversion
            try:
                variance = float(total_actual_portions) - float(total_planned_portions)
            except (TypeError, ValueError):
                variance = 0
            
            # Calculate revenue metrics for each plan item
            total_expected_revenue = 0
            total_actual_revenue = 0
            total_unsold_portions = 0
            
            for item in plan_items:
                try:
                    if not hasattr(item, 'dish') or not item.dish:
                        continue
                        
                    # Calculate expected revenue (declared portions * dish price)
                    portions = float(item.portions) if hasattr(item, 'portions') and item.portions is not None else 0
                    dish_price = float(item.dish.price) if hasattr(item.dish, 'price') and item.dish.price is not None else 0
                    expected_revenue = portions * dish_price
                    item.expected_revenue = expected_revenue
                    total_expected_revenue += expected_revenue
                    
                    # Calculate actual revenue (declared portions * dish price) using portions_sold
                    declared_portions = float(item.portions_sold) if hasattr(item, 'portions_sold') and item.portions_sold is not None else 0
                    item.declared_portions = declared_portions
                    actual_revenue = declared_portions * dish_price
                    item.actual_revenue = actual_revenue
                    total_actual_revenue += actual_revenue
                    
                    # Calculate unsold portions
                    unsold_portions = max(0, portions - declared_portions)
                    item.unsold_portions = unsold_portions
                    total_unsold_portions += unsold_portions
                    
                except (TypeError, ValueError, AttributeError) as e:
                    logger.error(f"Error calculating revenue for item {getattr(item, 'id', 'unknown')}: {str(e)}")
                    continue
            
            # Calculate revenue variance with safe type conversion
            try:
                revenue_variance = float(total_actual_revenue) - float(total_expected_revenue)
            except (TypeError, ValueError):
                revenue_variance = 0
            
            # Compute safe ingredients cost per portion for template usage
            try:
                ingredients_cost_per_portion = (
                    float(total_ingredients_cost) / float(total_planned_portions)
                ) if float(total_planned_portions) > 0 else 0
            except (TypeError, ValueError, ZeroDivisionError):
                ingredients_cost_per_portion = 0

            # Map declared/allocated quantities by product for display (if present)
            declared_by_product_id = {}
            try:
                allocations_qs = AllocatedRawMaterials.objects.filter(production=plan).select_related('raw_material')
                for alloc in allocations_qs:
                    product = alloc.raw_material
                    unit_name = getattr(product.unit, 'unit_name', 'unit')
                    unit_cost = float(product.cost or 0)
                    allocated_qty = float(alloc.quantity or 0)
                    declared_qty = float(alloc.remaining_quantity or 0) if hasattr(alloc, 'remaining_quantity') and alloc.remaining_quantity is not None else 0.0
                    declared_by_product_id[product.id] = {
                        'allocated_quantity': allocated_qty,
                        'allocated_cost': allocated_qty * unit_cost,
                        'declared_quantity': declared_qty,
                        'declared_cost': declared_qty * unit_cost,
                        'unit': unit_name,
                        'unit_cost': unit_cost,
                        'name': product.name,
                    }
            except Exception as e:
                logger.error(f"Error fetching allocations for declared values: {e}")

            # Enrich ingredient rows with allocated/declared/variance values for template simplicity
            try:
                for ing_row in ingredients:
                    product_id = ing_row.get('product_id')
                    mapping = declared_by_product_id.get(product_id, {})
                    unit_name = ing_row.get('unit') or mapping.get('unit') or 'unit'
                    ing_row['unit'] = unit_name
                    ing_row['allocated_quantity'] = mapping.get('allocated_quantity', 0)
                    ing_row['allocated_cost'] = mapping.get('allocated_cost', 0)
                    ing_row['declared_quantity'] = mapping.get('declared_quantity', 0)
                    ing_row['declared_cost'] = mapping.get('declared_cost', 0)
                    # Determine unit cost for monetary variance
                    try:
                        unit_cost_val = float(ing_row.get('cost_per_unit') if ing_row.get('cost_per_unit') is not None else mapping.get('unit_cost', 0))
                    except Exception:
                        unit_cost_val = 0.0
                    try:
                        expected_units = float(ing_row.get('quantity_required') or 0)
                        declared_units = float(ing_row.get('declared_quantity') or 0)
                        # Variance definition: expected - declared (positive means used less than expected)
                        variance_units = expected_units - declared_units
                        ing_row['variance_units'] = variance_units
                        ing_row['variance_positive_units'] = max(0.0, variance_units)
                        ing_row['variance_negative_units'] = abs(min(0.0, variance_units))
                        # Monetary variance
                        variance_amount = variance_units * unit_cost_val
                        ing_row['variance_amount'] = variance_amount
                        ing_row['variance_positive_amount'] = max(0.0, variance_amount)
                        ing_row['variance_negative_amount'] = abs(min(0.0, variance_amount))
                    except Exception:
                        ing_row['variance_units'] = 0
                        ing_row['variance_positive_units'] = 0
                        ing_row['variance_negative_units'] = 0
                        ing_row['variance_amount'] = 0
                        ing_row['variance_positive_amount'] = 0
                        ing_row['variance_negative_amount'] = 0
            except Exception as e:
                logger.error(f"Error enriching ingredient rows: {e}")

            # Compute per-dish variance totals and mark group headers
            try:
                dish_to_totals = {}
                for ing_row in ingredients:
                    dish_name_key = ing_row.get('dish_name') or 'Unknown Dish'
                    totals = dish_to_totals.setdefault(dish_name_key, {
                        'pos_amount': 0.0,
                        'neg_amount': 0.0,
                    })
                    totals['pos_amount'] += float(ing_row.get('variance_positive_amount') or 0)
                    totals['neg_amount'] += float(ing_row.get('variance_negative_amount') or 0)

                # Mark group header (first) and footer (last) items and attach per-dish totals
                seen_dishes = set()
                for idx, ing_row in enumerate(ingredients):
                    dish_name_key = ing_row.get('dish_name') or 'Unknown Dish'
                    # Header flag
                    if dish_name_key not in seen_dishes:
                        seen_dishes.add(dish_name_key)
                        ing_row['group_header'] = True
                    else:
                        ing_row['group_header'] = False
                    # Footer flag (if next item is different dish or this is last)
                    next_dish = None
                    if idx + 1 < len(ingredients):
                        next_dish = ingredients[idx + 1].get('dish_name') or 'Unknown Dish'
                    is_footer = (idx == len(ingredients) - 1) or (next_dish != dish_name_key)
                    ing_row['group_footer'] = is_footer
                    if is_footer:
                        dish_totals = dish_to_totals.get(dish_name_key, {'pos_amount': 0.0, 'neg_amount': 0.0})
                        ing_row['group_pos_total_amount'] = dish_totals['pos_amount']
                        ing_row['group_neg_total_amount'] = dish_totals['neg_amount']
                        # Calculate total variance for the group
                        ing_row['total_variance'] = dish_totals['pos_amount'] - dish_totals['neg_amount']

                # Overall totals
                total_positive_variance_amount = sum(v['pos_amount'] for v in dish_to_totals.values())
                total_negative_variance_amount = sum(v['neg_amount'] for v in dish_to_totals.values())
            except Exception as e:
                logger.error(f"Error computing dish variance totals: {e}")
                total_positive_variance_amount = 0.0
                total_negative_variance_amount = 0.0

            # Update consolidated ingredients with allocation and declaration data
            for rm in raw_materials:
                ingredient_name = rm.get('name')
                if ingredient_name in consolidated_ingredients:
                    consolidated_ingredients[ingredient_name].update({
                        'allocated_quantity': rm.get('quantity', 0),
                        'allocated_cost': rm.get('planned_amount', 0),
                        'declared_quantity': rm.get('expected_quantity', 0),
                        'declared_cost': rm.get('declared_amount', 0),
                        'variance_amount': rm.get('variance_amount', 0)
                    })
        
            # Convert consolidated ingredients to list for template
            ingredients_list = list(consolidated_ingredients.values())
        
            # Prepare context with safe defaults
            context = {
                'plan': plan,
                'plan_items': plan_items,
                'ingredients': ingredients_list,
                'raw_materials': raw_materials or [],
                'dish_ing': dish_ingredients,
                'total_planned_portions': total_planned_portions,
                'total_actual_portions': total_actual_portions,
                'total_production_cost': total_production_cost,
                'total_ingredients_cost': total_ingredients_cost,
                'ingredients_cost_per_portion': ingredients_cost_per_portion,
                'declared_by_product_id': declared_by_product_id,
                'variance': variance,
                'positive_variance': max(0, float(variance)),
                'negative_variance': abs(min(0, float(variance))),
                'total_expected_revenue': total_expected_revenue,
                'total_actual_revenue': total_actual_revenue,
                'total_unsold_portions': total_unsold_portions,
                'revenue_variance': revenue_variance,
                'total_positive_variance_amount': total_positive_variance_amount,
                'total_negative_variance_amount': total_negative_variance_amount,
            }
            
            logger.info("Context prepared successfully with calculated values")
            
        except Exception as e:
            logger.error(f"Error in final calculations: {str(e)}\n{traceback.format_exc()}")
            # Return a minimal context with error information
            return JsonResponse({
                'success': False,
                'error': 'Error in calculations',
                'details': str(e)
            }, status=500)
        
        # Debug logging
        logger.info(f"Context prepared successfully for plan {plan_id}")
        logger.info(f"Plan items count: {len(plan_items)}")
        
        return render(request, 'inventory/production_plan_detail_dropdown.html', context)
        
    except Production.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Production plan not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error in production_plan_detail_ajax: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def production_plan_allocations_ajax(request, plan_id):
    """AJAX view for production plan allocations"""
    from datetime import datetime, timedelta
    from decimal import Decimal
    
    try:
        # Get the specific production plan
        plan = Production.objects.get(id=plan_id, branch=request.user.branch)
        
        # Get production items for this plan
        plan_items = ProductionItems.objects.filter(production=plan)
        
        # Get ingredients/raw materials allocations for this plan
        allocations = []
        for item in plan_items:
            if hasattr(item, 'dish') and item.dish:
                # Get ingredients for this dish
                dish_ingredients = Ingredient.objects.filter(dish=item.dish)
                for ing in dish_ingredients:
                    allocations.append({
                        'dish_name': item.dish.name,
                        'planned_portions': item.portions or 0,
                        'actual_portions': item.actual_quantity or 0,
                        'ingredient_name': ing.minor_raw_material.name,
                        'quantity_per_portion': ing.quantity,
                        'total_quantity_required': ing.quantity * (item.portions or 0),
                        'unit': ing.minor_raw_material.unit.unit_name,
                        'cost_per_unit': ing.minor_raw_material.cost,
                        'total_cost': ing.quantity * (item.portions or 0) * ing.minor_raw_material.cost,
                        'stock_available': ing.minor_raw_material.quantity_in_stock or 0,
                        'stock_status': 'Sufficient' if (ing.minor_raw_material.quantity_in_stock or 0) >= (ing.quantity * (item.portions or 0)) else 'Insufficient'
                    })
        
        context = {
            'plan': plan,
            'allocations': allocations,
            'total_items': plan_items.count(),
            'total_ingredients': len(allocations),
            'total_cost': sum(alloc['total_cost'] for alloc in allocations),
            'insufficient_stock_count': len([alloc for alloc in allocations if alloc['stock_status'] == 'Insufficient'])
        }
        
        return render(request, 'inventory/production_plan_allocations.html', context)
        
    except Production.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Production plan not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error in production_plan_allocations_ajax: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_only_required
def create_production_plan_ajax(request):
    """AJAX version of create_production_plan"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(data)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)

        items = data.get('cart', [])
        if not items or not isinstance(items, list):
            return JsonResponse({'success': False, 'message': 'Invalid data: items should be a list'}, status=400)
        
        production_plan = None
        auto_confirm = data.get('auto', '')

        if Production.objects.filter(declared=False, branch=request.user.branch).exists():
            pass
            # return JsonResponse({'success': False, 'message': 'Please declare all the production plans you have.'}, status=400)

        # Create a new production plan
        production_plan = Production.objects.create(status=False, declared=False, branch=request.user.branch)

        logger.info(f"production_plan: {production_plan.branch}")

        if auto_confirm:
            if data.get('id'):
                production_plan = Production.objects.get(id = data.get('id'), branch=request.user.branch)
            else:
                production_latest = Production.objects.filter(date_created = datetime.date.today(), branch=request.user.branch).order_by('-time_created').first()
                if production_latest:
                    production_plan = production_latest
                else:
                    return JsonResponse({'success': False, 'message': 'No production Plan for Today.'}, status=400)
        else:
            # Create a new production plan
            production_plan = Production.objects.create(status=False, declared=False, branch=request.user.branch)

        # Process each item in the cart
        for item in items:
            dish_id = item.get('dish_id')
            portions = item.get('portions', 0)
            
            try:
                dish = Dish.objects.get(id=dish_id, branch=request.user.branch)
                
                # Calculate total cost based on dish cost and portions
                total_cost = dish.cost * portions if dish.cost else 0
                
                # Create production item
                ProductionItems.objects.create(
                    production=production_plan,
                    dish=dish,
                    portions=portions,
                    total_cost=total_cost
                )
                
            except Dish.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'Dish with ID {dish_id} not found'}, status=400)

        return JsonResponse({
            'success': True, 
            'message': f'Production plan {production_plan.production_plan_number} created successfully!',
            'production_plan_id': production_plan.id
        })
    
    # GET request - show the form
    dishes = Dish.objects.filter(branch=request.user.branch)
    form = ProductionPlanInlineForm()
    form.fields['dish'].queryset = dishes
    context = {
        'dishes': dishes,
        'form': form
    }
    return render(request, 'inventory/create_production_plan_content.html', context)

@login_required
def dish_list_ajax(request):
    """AJAX version of dish_list"""
    dishes = Dish.objects.filter(branch=request.user.branch)
    context = {
        'dishes': dishes
    }
    return render(request, 'inventory/dish_list_content.html', context)

@login_required
def meal_list_ajax(request):
    """AJAX version of meal_list"""
    meals = Meal.objects.filter(branch=request.user.branch)
    context = {
        'meals': meals
    }
    return render(request, 'inventory/meal_list_content.html', context)

@login_required
def chef_checklist_ajax(request):
    """AJAX version of chef_checklist"""
    products = Product.objects.filter(branch=request.user.branch).order_by('name')
    context = {
        'products': products
    }
    return render(request, 'inventory/chef_checklist_content.html', context)

@login_required
def test_ajax_view(request):
    """Simple test view for debugging AJAX"""
    return render(request, 'inventory/test_content.html', {})

@login_required
@chef_only_required
def add_dish_ajax(request):
    """AJAX version of add_dish for dynamic loading in chef interface"""
    form = IngredientForm()
    dish_form = DishForm()
    
    if request.method == 'GET':
        r_m = Product.objects.filter(raw_material=True, branch=request.user.branch)
        context = {
            'r_m': r_m,
            'form': form,
            'dish_form': dish_form
        }
        return render(request, 'inventory/add_dish_content.html', context)
    
    # POST handling remains the same as original add_dish
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(data)
            cart = data.get('cart')
        
            dish_name = data.get('name')
            portion_multiplier = data.get('portion_multiplier')
            cost = data.get('dish_cost')
            selling_price = data.get('selling_price')
            category = data.get('category')

            logger.info(cart)
            
            if not dish_name or not portion_multiplier or not cost or not selling_price:
                return JsonResponse({'success': False, 'message': f'Please fill all the missing data'}, status=400)
            
            with transaction.atomic():
                dish = Dish.objects.create(
                    cost = cost,
                    name = dish_name,
                    portion_multiplier = portion_multiplier,
                    price = selling_price,
                    category=category,
                    branch=request.user.branch
                )
                
                for item in cart:
                    raw_material = Product.objects.get(name=item.get('raw_material'), branch=request.user.branch)
                    Ingredient.objects.create(
                        dish=dish,
                        note=item.get('note'),
                        minor_raw_material=raw_material,
                        quantity=item.get('quantity'),
                    )
                
                return JsonResponse({
                    'success': True, 
                    'message': f'Dish {dish.name} created successfully!',
                    'dish_id': dish.id
                })
                
        except Exception as e:
            logger.error(f"Error creating dish: {e}")
            return JsonResponse({'success': False, 'message': f'{e}'}, status=400)

@login_required
@chef_or_stores_view_required
def production_plan_pdf_template(request, plan_id):
    plan = get_object_or_404(Production, id=plan_id)
    
    # Get production items
    plan_items = ProductionItems.objects.filter(production=plan).select_related('dish')
    
    total_planned_portions = plan_items.aggregate(
        total=Coalesce(Sum('portions', output_field=models.FloatField()), 0, output_field=models.FloatField())
    )['total'] or 0
    
    total_actual_portions = plan_items.aggregate(
        total=Coalesce(Sum('portions_sold', output_field=models.FloatField()), 0, output_field=models.FloatField())
    )['total'] or 0
    
    total_production_cost = plan_items.aggregate(
        total=Coalesce(Sum('total_cost', output_field=models.DecimalField(max_digits=10, decimal_places=2)), 0, 
                      output_field=models.DecimalField(max_digits=10, decimal_places=2))
    )['total'] or 0
    
    variance = total_actual_portions - total_planned_portions
    # Prepare ingredients data
    ingredients = []
    total_positive_variance_amount = 0
    total_negative_variance_amount = 0
    total_ingredients_cost = 0
    
    for item in plan_items:
        if not item.dish:
            continue
            
        # Add group header for dish
        ingredients.append({
            'group_header': True,
            'dish_name': item.dish.name
        })
        
        dish_pos_total = 0
        dish_neg_total = 0
        
        # Get ingredients for this dish
        dish_ingredients = Ingredient.objects.filter(dish=item.dish).select_related('minor_raw_material', 'minor_raw_material__unit')
        
        for ing in dish_ingredients:
            unit_name = ing.minor_raw_material.unit.unit_name if ing.minor_raw_material and ing.minor_raw_material.unit else 'unit'
            
            # Calculate quantities
            allocated_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier) if item.portions else 0
            allocated_cost = allocated_quantity * float(ing.cost or 0)
            
            quantity_required = ing.quantity
            total_cost = quantity_required * float(ing.cost or 0)
            total_ingredients_cost += total_cost
            
            declared_quantity = ing.quantity * (item.portions_sold / item.dish.portion_multiplier) if item.portions_sold else 0
            declared_cost = declared_quantity * float(ing.cost or 0)
            
            # Calculate variances
            variance_amount = declared_cost - allocated_cost
            variance_positive_amount = variance_amount if variance_amount > 0 else 0
            variance_negative_amount = abs(variance_amount) if variance_amount < 0 else 0
            
            dish_pos_total += variance_positive_amount
            dish_neg_total += variance_negative_amount
            
            total_positive_variance_amount += variance_positive_amount
            total_negative_variance_amount += variance_negative_amount
            
            ingredients.append({
                'name': ing.minor_raw_material.name if ing.minor_raw_material else 'N/A',
                'unit': unit_name,
                'allocated_quantity': allocated_quantity,
                'allocated_cost': allocated_cost,
                'quantity_required': quantity_required,
                'total_cost': total_cost,
                'declared_quantity': declared_quantity,
                'declared_cost': declared_cost,
                'variance_positive_amount': variance_positive_amount,
                'variance_negative_amount': variance_negative_amount,
                'group_footer': False
            })
        
        # Add group footer with dish totals
        ingredients.append({
            'group_footer': True,
            'dish_name': item.dish.name,
            'group_pos_total_amount': dish_pos_total,
            'group_neg_total_amount': dish_neg_total
        })
    
    context = {
        'plan': plan,
        'plan_items': plan_items,
        'total_planned_portions': total_planned_portions,
        'total_actual_portions': total_actual_portions,
        'total_production_cost': total_production_cost,
        'variance': variance,
        'ingredients': ingredients,
        'total_positive_variance_amount': total_positive_variance_amount,
        'total_negative_variance_amount': total_negative_variance_amount,
        'total_ingredients_cost': total_ingredients_cost,
    }
    
    return render(request, 'inventory/production_plan_pdf_template.html', context)






def view_production_plan(request, pp_id):
    """
    View production plan with detailed comparison of planned vs produced quantities
    Shows variance analysis with modern table design
    """
    try:
        production_plan = Production.objects.get(id=pp_id, branch=request.user.branch)
        production_items = ProductionItems.objects.filter(production=production_plan)
        
        # Get all ingredients for the dishes in this production plan
        dish_ingredients = Ingredient.objects.filter(
            dish__in=[item.dish for item in production_items],
            minor_raw_material__branch=request.user.branch
        )
        
        # Prepare data for the variance table
        variance_data = []
        
        # Process dishes/portions
        for item in production_items:
            planned_portions = item.planned_portions or 0
            produced_portions = item.portions or 0
            variance = produced_portions - planned_portions
            
            variance_data.append({
                'type': 'Portion',
                'name': item.dish.name,
                'planned_quantity': planned_portions,
                'produced_quantity': produced_portions,
                'variance': variance,
                'unit': 'portions',
                'date': production_plan.date_created,
                'time': production_plan.time_created
            })
        
        # Process ingredients
        for item in production_items:
            for ing in dish_ingredients.filter(dish=item.dish):
                # Calculate planned quantity based on planned portions
                planned_quantity = ing.quantity * (item.planned_portions / item.dish.portion_multiplier) if item.planned_portions else 0
                
                # Calculate produced quantity based on actual portions
                produced_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier) if item.portions else 0
                
                variance = produced_quantity - planned_quantity
                
                variance_data.append({
                    'type': 'Ingredient',
                    'name': f"{item.dish.name} - {ing.minor_raw_material.name}",
                    'planned_quantity': round(planned_quantity, 2),
                    'produced_quantity': round(produced_quantity, 2),
                    'variance': round(variance, 2),
                    'unit': ing.minor_raw_material.unit.unit_name if ing.minor_raw_material.unit else 'units',
                    'date': production_plan.date_created,
                    'time': production_plan.time_created
                })
        
        # Sort by date and time (most recent first)
        variance_data.sort(key=lambda x: (x['date'], x['time']), reverse=True)
        
        context = {
            'production_plan': production_plan,
            'variance_data': variance_data,
            'total_items': len(variance_data),
            'positive_variance_count': len([item for item in variance_data if item['variance'] > 0]),
            'negative_variance_count': len([item for item in variance_data if item['variance'] < 0]),
            'zero_variance_count': len([item for item in variance_data if item['variance'] == 0]),
        }
        
        return render(request, 'inventory/view_production_plan.html', context)
        
    except Production.DoesNotExist:
        messages.error(request, f'Production Plan with ID: {pp_id} does not exist.')
        return redirect('inventory:production_plans')
    except Exception as e:
        messages.error(request, f'Error loading production plan: {str(e)}')
        return redirect('inventory:production_plans')

@login_required
@chef_or_stores_view_required
def production_analysis_api(request):
    """
    API endpoint to provide production analysis data for the analysis page
    Returns comprehensive data for all production plans with filtering capabilities
    """
    try:
        from datetime import datetime, timedelta
        import json
        
        # Get filter parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        status_filter = request.GET.get('status', 'all')
        
        # Base queryset - get all production plans for the user's branch
        production_plans = Production.objects.filter(branch=request.user.branch)
        
        # Apply date filters if provided
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                production_plans = production_plans.filter(date_created__range=[start, end])
            except ValueError:
                pass
        
        # Apply status filter
        if status_filter == 'confirmed':
            production_plans = production_plans.filter(status=True)
        elif status_filter == 'declared':
            production_plans = production_plans.filter(declared=True)
        elif status_filter == 'completed':
            production_plans = production_plans.filter(status=True, declared=True)
        
        # Order by most recent first
        production_plans = production_plans.order_by('-date_created', '-time_created')
        
        analysis_data = []
        
        for plan in production_plans:
            # Get production items for this plan
            production_items = ProductionItems.objects.filter(production=plan)
            
            # Get all ingredients for the dishes in this production plan
            dish_ingredients = Ingredient.objects.filter(
                dish__in=[item.dish for item in production_items],
                minor_raw_material__branch=request.user.branch
            )
            
            # Process dishes/portions
            for item in production_items:
                # Planned portions come from the database (what chef planned)
                planned_portions = item.planned_portions or 0
                # Produced portions are what was actually declared by stores person
                produced_portions = item.portions or 0
                variance = produced_portions - planned_portions
                
                # Determine status
                if plan.status and plan.declared:
                    status = 'completed'
                elif plan.status:
                    status = 'confirmed'
                elif plan.declared:
                    status = 'declared'
                else:
                    status = 'pending'
                
                analysis_data.append({
                    'id': f"{plan.id}-{item.id}-portion",
                    'plan_number': plan.production_plan_number,
                    'date': plan.date_created.isoformat(),
                    'item_name': item.dish.name,
                    'type': 'Portion',
                    'planned_quantity': planned_portions,
                    'produced_quantity': produced_portions,
                    'variance': variance,
                    'unit': 'portions',
                    'status': status
                })
            
            # Process ingredients
            for item in production_items:
                for ing in dish_ingredients.filter(dish=item.dish):
                    # Planned portions come from the database (what chef planned)
                    planned_portions = item.planned_portions or 0
                    
                    # Calculate planned quantity based on planned portions
                    planned_quantity = ing.quantity * (planned_portions / item.dish.portion_multiplier) if planned_portions else 0
                    
                    # Calculate produced quantity based on actual portions (what was declared)
                    produced_quantity = ing.quantity * (item.portions / item.dish.portion_multiplier) if item.portions else 0
                    
                    variance = produced_quantity - planned_quantity
                    
                    # Determine status
                    if plan.status and plan.declared:
                        status = 'completed'
                    elif plan.status:
                        status = 'confirmed'
                    elif plan.declared:
                        status = 'declared'
                    else:
                        status = 'pending'
                    
                    analysis_data.append({
                        'id': f"{plan.id}-{item.id}-{ing.id}",
                        'plan_number': plan.production_plan_number,
                        'date': plan.date_created.isoformat(),
                        'item_name': f"{item.dish.name} - {ing.minor_raw_material.name}",
                        'type': 'Ingredient',
                        'planned_quantity': round(planned_quantity, 2),
                        'produced_quantity': round(produced_quantity, 2),
                        'variance': round(variance, 2),
                        'unit': ing.minor_raw_material.unit.unit_name if ing.minor_raw_material.unit else 'units',
                        'status': status
                    })
        
        return JsonResponse({
            'success': True,
            'data': analysis_data,
            'total_count': len(analysis_data),
            'plans_count': len(set(item['plan_number'] for item in analysis_data))
        })
        
    except Exception as e:
        logger.error(f"Error in production analysis API: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def stock_analysis_api(request):
    """API endpoint for stock analysis data"""
    try:
        # Get filter parameters
        product_type = request.GET.get('product_type')
        stock_status = request.GET.get('stock_status')
        search = request.GET.get('search')
        
        # Base queryset - combine ingredients and dishes
        data = []
        
        # Get ingredients
        ingredients = Ingredient.objects.all()
        if search:
            ingredients = ingredients.filter(name__icontains=search)
        
        for ingredient in ingredients:
            # Determine stock status
            current_stock = ingredient.current_stock or 0
            min_stock = ingredient.min_stock_level or 0
            
            if current_stock <= 0:
                stock_status_value = 'out_of_stock'
            elif current_stock <= min_stock:
                stock_status_value = 'low_stock'
            else:
                stock_status_value = 'in_stock'
            
            # Apply filters
            if stock_status and stock_status != 'all' and stock_status_value != stock_status:
                continue
                
            if product_type and product_type != 'all':
                if product_type == 'ingredient' and ingredient.type != 'ingredient':
                    continue
                elif product_type == 'raw' and ingredient.type != 'raw':
                    continue
            
            data.append({
                'id': f"ingredient_{ingredient.id}",
                'name': ingredient.name,
                'type': ingredient.type or 'ingredient',
                'description': ingredient.description or '',
                'current_stock': current_stock,
                'min_stock_level': min_stock,
                'stock_status': stock_status_value,
                'unit': ingredient.unit,
                'last_updated': ingredient.updated_at.isoformat() if ingredient.updated_at else ingredient.created_at.isoformat()
            })
        
        # Get dishes (finished products)
        dishes = Dish.objects.all()
        if search:
            dishes = dishes.filter(name__icontains=search)
        
        for dish in dishes:
            # For dishes, we might not have stock tracking, so we'll show as available
            current_stock = getattr(dish, 'current_stock', 0) or 0
            min_stock = getattr(dish, 'min_stock_level', 0) or 0
            
            if current_stock <= 0:
                stock_status_value = 'out_of_stock'
            elif current_stock <= min_stock:
                stock_status_value = 'low_stock'
            else:
                stock_status_value = 'in_stock'
            
            # Apply filters
            if stock_status and stock_status != 'all' and stock_status_value != stock_status:
                continue
                
            if product_type and product_type != 'all':
                if product_type == 'finished' and dish.type != 'finished':
                    continue
            
            data.append({
                'id': f"dish_{dish.id}",
                'name': dish.name,
                'type': 'finished',
                'description': dish.description or '',
                'current_stock': current_stock,
                'min_stock_level': min_stock,
                'stock_status': stock_status_value,
                'unit': 'portions',
                'last_updated': dish.updated_at.isoformat() if hasattr(dish, 'updated_at') and dish.updated_at else dish.created_at.isoformat()
            })
        
        # Sort by name
        data.sort(key=lambda x: x['name'])
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def stock_item_details_api(request, item_id):
    """API endpoint for detailed stock item information"""
    try:
        item_type, item_pk = item_id.split('_', 1)
        
        if item_type == 'ingredient':
            item = Ingredient.objects.get(id=item_pk)
            usage_history = []  # You can implement usage history tracking here
            
            data = {
                'id': item.id,
                'name': item.name,
                'type': item.type or 'ingredient',
                'description': item.description or '',
                'current_stock': item.current_stock or 0,
                'min_stock_level': item.min_stock_level or 0,
                'unit': item.unit,
                'stock_status': get_stock_status(item.current_stock or 0, item.min_stock_level or 0),
                'last_updated': item.updated_at.isoformat() if item.updated_at else item.created_at.isoformat(),
                'usage_history': usage_history
            }
        elif item_type == 'dish':
            item = Dish.objects.get(id=item_pk)
            usage_history = []  # You can implement usage history tracking here
            
            data = {
                'id': item.id,
                'name': item.name,
                'type': 'finished',
                'description': item.description or '',
                'current_stock': getattr(item, 'current_stock', 0) or 0,
                'min_stock_level': getattr(item, 'min_stock_level', 0) or 0,
                'unit': 'portions',
                'stock_status': get_stock_status(getattr(item, 'current_stock', 0) or 0, getattr(item, 'min_stock_level', 0) or 0),
                'last_updated': item.updated_at.isoformat() if hasattr(item, 'updated_at') and item.updated_at else item.created_at.isoformat(),
                'usage_history': usage_history
            }
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid item type'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except (Ingredient.DoesNotExist, Dish.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': 'Item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def production_item_details_api(request, item_id):
    """API endpoint for detailed production item information"""
    try:
        # Parse the item_id to extract plan_id, item_id, and type
        parts = item_id.split('-')
        if len(parts) >= 3:
            plan_id = parts[0]
            item_id_part = parts[1]
            item_type = parts[2]
            
            if item_type == 'portion':
                # Handle dish/portion items
                production_item = ProductionItems.objects.get(id=item_id_part)
                dish = production_item.dish
                
                data = {
                    'id': production_item.id,
                    'item_name': dish.name,
                    'type': 'Dish',
                    'plan_number': production_item.production.production_plan_number,
                    'date': production_item.production.date_created.isoformat(),
                    'planned_quantity': production_item.planned_portions or 0,
                    'produced_quantity': production_item.portions or 0,
                    'variance': (production_item.portions or 0) - (production_item.planned_portions or 0),
                    'unit': 'portions',
                    'status': get_production_status(production_item.production),
                    'notes': production_item.notes or '',
                    'responsible_person': production_item.production.created_by.username if production_item.production.created_by else 'Not specified'
                }
            else:
                # Handle ingredient items
                data = {
                    'id': item_id,
                    'item_name': 'Ingredient Item',
                    'type': 'Ingredient',
                    'plan_number': 'N/A',
                    'date': 'N/A',
                    'planned_quantity': 0,
                    'produced_quantity': 0,
                    'variance': 0,
                    'unit': 'N/A',
                    'status': 'N/A',
                    'notes': 'Ingredient details not available',
                    'responsible_person': 'Not specified'
                }
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid item ID format'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except ProductionItems.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Production item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def notifications_api(request):
    """API endpoint for notifications"""
    try:
        # For now, we'll return mock notifications
        # In a real implementation, you'd have a Notification model
        notifications = [
            {
                'id': 1,
                'title': 'Low Stock Alert',
                'message': 'Tomatoes are running low on stock',
                'timestamp': '2024-01-15T10:30:00Z',
                'type': 'stock_alert'
            },
            {
                'id': 2,
                'title': 'Production Plan Confirmed',
                'message': 'Production plan #123 has been confirmed by chef',
                'timestamp': '2024-01-15T09:15:00Z',
                'type': 'production_update'
            }
        ]
        
        return JsonResponse({
            'success': True,
            'notifications': notifications
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def clear_notifications_api(request):
    """API endpoint to clear notifications"""
    if request.method == 'POST':
        try:
            return JsonResponse({
                'success': True,
                'message': 'Notifications cleared successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    else:
        return JsonResponse({
            'success': False,
            'error': 'Method not allowed'
        }, status=405)

def get_stock_status(current_stock, min_stock):
    """Helper function to determine stock status"""
    if current_stock <= 0:
        return 'out_of_stock'
    elif current_stock <= min_stock:
        return 'low_stock'
    else:
        return 'in_stock'


@login_required
def stocktake(request):
    """View for stocktaking interface"""
    
    products = Product.objects.filter(branch=request.user.branch).order_by('name')
    stocktakes = StockTake.objects.filter(branch=request.user.branch).order_by('-date')
    context = {
        'products': products,
        'stocktakes':stocktakes,
        'form':CreateStockTakeForm()
    }

    if request.method == "POST":
        """
            {
                'conductor':str,
                'users':list
            }
        """
        try:
            conductor = request.POST.get('conductor')
            users = request.POST.getlist('users')
            
            # validation
            if not conductor:
                return JsonResponse({
                    'success': False,
                    'error': 'Conductor is required'
                }, status=400)
            
            if not users:
                return JsonResponse({
                    'success': False,
                    'error': 'At least one'  
                })

            # Create a new stock take entry
            stock_take = StockTake.objects.create(
                conductor_id=conductor,
                branch=request.user.branch
            )
            
            for user in users:
                stock_take.users.add(user)
            stock_take.save()

            # create initial stocktake item
            for product in Product.objects.filter(branch=request.user.branch):
                item = StockTakeItem.objects.create(
                    stock_take=stock_take,
                    product=product,
                    recorded_quantity=0,
                    actual_quantity=product.quantity
                )
                
                print(product.quantity, item.actual_quantity)
            
            logger.success(f'Stock take created successfully')

            return render(request, 'stocktake/stocktake.html', context)

        except Exception as e:
            logger.error(f'Failed to process stocktake: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Failed to create stock take'
            })
            
   
    return render(request, 'stocktake/stocktake.html', context) 


@login_required
def stocktake_detail(request, stocktake_id):
    stocktake = StockTake.objects.get(id=stocktake_id)
    stock_take = StockTakeItem.objects.filter(stock_take__id=stocktake_id, stock_take__branch=request.user.branch).order_by('-actual_quantity')

    context = {
        'stocktake':stocktake,
        'stocktake_items': stock_take
    }
    return render(request, 'stocktake/stocktake_detail.html', context)
            
@login_required
def record_stock_take(request):
    if request.method == "POST":
        """
            stock_take_id: int,
            quantity: int
        """
        try:
            data = json.loads(request.body)
            stock_take_id = data.get('stocktake_id')
            stock_take_item = int(data.get('product_id'))
            quantity = data.get('quantity')
            
            stock_take = StockTake.objects.get(id=stock_take_id, branch=request.user.branch)
            stock_take_item = StockTakeItem.objects.get(id=stock_take_item, stock_take=stock_take)

            variance = float(quantity) - stock_take_item.actual_quantity 
            
            stock_take_item.recorded_quantity = quantity
            stock_take_item.variance = variance
            stock_take_item.success = True if variance == 0 else False

            stock_take_item.save()

            logger.success(f'Stock take recorded successfully')

            return JsonResponse({
                'success': True,
                'item_id': stock_take_item.id,
                'difference':variance,
                'message': 'Stock take recorded successfully'
            })
            
        except Exception as e:
            logger.error(f'Failed to record stock take: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Failed to record stock take'
            })
            
@login_required
def accept_variance(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            stock_take_item_id = data.get('item_id')
            note = data.get('note', '')
            
            print(stock_take_item_id, note)
            stock_take_item = StockTakeItem.objects.get(id=stock_take_item_id)

            stock_take_item.accept_variance = True
            stock_take_item.success = True
            stock_take_item.note = note
            
            stock_take_item.save()

            logger.success(f'Variance accepted successfully')

            return JsonResponse({
                'success': True,
                'message': 'Variance accepted successfully'
            })

        except Exception as e:
            logger.error(f'Failed to accept variance: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Failed to accept variance'
            })

@login_required
def undo_record_stock_take(request):
    if request.method == "POST":
        """
            stocktake_id: int,
        """
        try:
            data = json.loads(request.body)
            stock_take_id = data.get('stocktake_id')
            print(data)

            stock_take_item = StockTakeItem.objects.get(id=stock_take_id)
            
            stock_take_item.recorded_quantity = 0
            stock_take_item.variance = 0
            stock_take_item.success = False
            stock_take_item.accept_variance = False
            stock_take_item.note = ''

            stock_take_item.save()

            logger.success(f'Stock take undone successfully')

            return JsonResponse({
                'success': True,
                'item_id': stock_take_item.id,
                'message': 'Stock take undone successfully'
            })
            
        except Exception as e:
            logger.error(f'Failed to undo stock take: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Failed to undo stock take'
            })