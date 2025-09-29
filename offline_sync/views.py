from django.shortcuts import render
from finance.models import Sale, SaleItem, CashBook, Change
from inventory.models import Logs, Product, ProductionLogs, Dish, Meal
from rest_framework import viewsets
from rest_framework.respone import Response
from .serializers import SaleSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from loguru import logger
from django.shortcuts import get_object_or_404
from .models import SyncLog
from django.db import transaction
from django.core.cache import cache
from django.utils.timezone import localdate
from pos.tasks import lowStockNotifications, updateTakeAway
from django.utils import timezone
import json
from decimal import Decimal
from finance.serialiers import *

today = localdate()

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

class ChangeView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Change.objects.filter(cashier=self.request.user)
    
    @action(detail=False, methods=['post'])
    def sync(self, request):
        """
        Handle offline sync for change collection
        Payload format:
        {
            "data": [{
                "operation": "collect",
                "change_id": "id",
                "amount": 100.00,
                "timestamp": "2025-09-08T10:00:00Z"
            }],
            "last_sync": "2025-09-08T09:00:00Z"
        }
        """
        sync_data = request.data.get('data', [])
        last_sync = request.data.get('last_sync')
        
        # Get pending changes since last sync
        if last_sync:
            server_changes = Change.objects.filter(
                cashier=request.user,
                timestamp__gt=last_sync,
                collected=False
            )
        else:
            server_changes = Change.objects.filter(
                cashier=request.user,
                collected=False
            )
        
        sync_errors = []
        
        # Process client changes
        for item in sync_data:
            try:
                if item['operation'] == 'collect':
                    change_id = item['change_id']
                    amount = Decimal(item['amount'])
                    
                    with transaction.atomic():
                        change = Change.objects.get(
                            id=change_id,
                            sale__branch=request.user.branch
                        )
                        
                        if amount == change.amount:
                            change.collected = True
                            change.cashier_give = request.user
                        elif amount < change.amount:
                            change.amount -= Decimal(amount)
                            change.cashier_give = request.user
                        else:
                            sync_errors.append({
                                'change_id': change_id,
                                'error': 'Amount collected is more than the change amount'
                            })
                            continue
                            
                        change.save()
                        
                        SyncLog.objects.create(
                            user=request.user,
                            operation='collect_change',
                            model_name='Change',
                            object_id=change_id
                        )
                        
                        logger.success(f'Change created: {}')
                
            except Change.DoesNotExist:
                sync_errors.append({
                    'change_id': item.get('change_id'),
                    'error': 'Change not found'
                })
            except Exception as e:
                sync_errors.append({
                    'change_id': item.get('change_id'),
                    'error': str(e)
                })
                # Log failed sync
                SyncLog.objects.create(
                    user=request.user,
                    operation='collect_change',
                    model_name='Change',
                    object_id=item.get('change_id'),
                    success=False,
                    error_message=str(e)
                )
        
        return Response({
            'pending_changes': ChangeSerializer(server_changes, many=True).data,
            'sync_errors': sync_errors,
            'sync_timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
    
    logger.success(f'Change created for client: {client_data.get('name')}')

class SaleView(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = IsAuthenticated
    
    def get_queryset(self, request):
        return Sale.objects.filter(user=request.user)
    
    @action(detail=False, methods=['post'])
    def sync(self, request):
        sale_data = request.data.get('data', [])
        last_sync = request.data.get('last_sync')
        
        if last_sync:
            server_changes = Sale.objects.filter(
                user=request.user,
                updated_at__gt=last_sync
            )
        else:
            server_changes = Sale.objects.filter(user=request.user)
            
        conflicts = []
        try:
            # check_status = SaleAuthorization.objects.get(auth_date = datetime.date.today(), auth_granted = True)
            check_status = True
            #today_plan = Production.objects.filter(date_created=datetime.date.today(), declared=True, status=True).first()
            if check_status:
                data = json.loads(request.body)
                items = data['items']
                staff = data['staff']
                change_data = data.get('change_data')
                order_type = data['order_type']
                cash_type = data['cash_type']
                logger.info(order_type)
                logger.info(cash_type)
                logger.info(items)
                received_amount = data.get('received_amount')
                meal_bool = data.get('meal')

                sub_total = sum(item['price'] * item['quantity'] for item in items)
                tax = sub_total * 0.15 
                
                total_amount = sub_total

                balance=0
                if change_data:
                    change_data = change_data[0]
                    balance = change_data['balance']
                
                if staff:
                    received_amount = 0.00

                with transaction.atomic():
                    product = None

                    if staff:
                        logger.info(f'sale is staff: {staff} : {total_amount}')
                        sale = Sale.objects.create(
                            branch = request.user.branch,
                            total_amount=total_amount,
                            tax=tax,
                            sub_total=sub_total,
                            cashier=request.user,
                            staff=True,
                            change=0.00,
                            amount_paid=received_amount
                        )
                    else:
                        sale = Sale.objects.create(
                            branch = request.user.branch,
                            total_amount=total_amount,
                            tax=tax,
                            sub_total=sub_total,
                            cashier=request.user,
                            staff=False,
                            change=balance,
                            amount_paid=received_amount,
                            cash_type= cash_type
                        )

                    logger.info(sale)

                    # daily_productions = Production.objects.filter(date_created=today).order_by('time_created')

                    # logger.info(f'daily productions: {daily_productions}')
                    task_list = []
                    take_away_bool = False
                    for item in items:
                        if not item['type']:

                            logger.info('Processing meal or dish')
                            
                            meal = None
                            dish = None

                            logger.info(f'Looking for meal with id {item['meal_id']} or dishes with id {item['meal_id']}')

                            if item.get('meal'): 
                                meal_id = item['meal_id'].split('-')[1]

                                meal = get_object_or_404(Meal, id=meal_id, branch = request.user.branch)
                                logger.info(f'Sale for meal: {meal}')
                            elif item.get('dish'):
                                dish_id = item['meal_id'].split('-')[1] 
                                dish = get_object_or_404(Dish, id=dish_id, branch = request.user.branch)
                                logger.info(f'Sale for dish: {dish}')
                            else:
                                raise ValueError('Invalid item type: Neither meal nor dish specified.')
                            
                            if staff:
                                sale_item = SaleItem.objects.create(
                                    sale=sale,
                                    quantity=item['quantity'],
                                    price=meal.price if meal else dish.price,
                                )
                            else:
                                sale_item = SaleItem.objects.create(
                                    sale=sale,
                                    quantity=item['quantity'],
                                    price=meal.price if meal else dish.price,
                                )

                            if order_type == 'takeaway':
                                """
                                    cache total takeaway orders

                                    use name instead of id 

                                    use redis to to cache kylelite , fork/spoon , plastic bag

                                    check if item exists in cache memory  if not check in db and dump to redis cache memory
                                """
                                if not take_away_bool:
                                    if cache.get('Take_Away_Total'):
                                        cache_total = cache.get('Take_Away_Total') 
                                        cache_total += 1
                                        cache.set('Take_Away_Total', cache_total, timeout= 46000)
                                    else:
                                        cache.set('Take_Away_Total', 1, timeout= 46000)
                                take_away_bool = True

                                take_away_items = ['Kylites #25', 'Spoons / Fork', 'Plastic bags']
                                cache_qnty = 0

                                for name in take_away_items:
                                    cached_data = cache.get(name)
                                    logger.info({'Cached Data Raw': cached_data})

                                    if cached_data:
                                        quantity_in_cache = cached_data.get("Quantity", 0)
                                        logger.info({'Cached Quantity': quantity_in_cache})

                                        
                                        cache_qnty = quantity_in_cache - item['quantity']

                                        # Update the cache
                                        cache.set(name, {'Quantity': cache_qnty}, timeout = 36000)
                                        logger.info({'Updated Quantity': cache_qnty})
                                        task_list.append(
                                            {
                                                'Product_Name': name,
                                                'Quantity': item['quantity']
                                            }
                                        )
                                    else:
                                        take_away = Product.objects.get(name__icontains=name, branch = request.user.branch)
                                        logger.info({f'Product Takeaway Stuff': take_away.name})

                                        take_away.quantity -= item['quantity']
                                        take_away.save()

                                        # Initialize in cache
                                        cache.set(name, {'Quantity': take_away.quantity}, timeout = 36000)

                                        """   
                                        logger.info({f'ID : {id}'})
                                        take_away = Product.objects.get(id = id)
                                        logger.info({f'Product Takeaway Stuff : {take_away.name}'})
                                        take_away.quantity -= item['quantity']
                                        take_away.save()
                                        """    
                            if meal:
                                if staff:
                                    # deduct_current_production_plan(request, meal=meal.name, dish=None, product=None, quantity=item['quantity'], staff=True)
                                    sale_item.meal=meal
                                else:
                                    # deduct_current_production_plan(request, meal=meal.name, dish=None, product=None, quantity=item['quantity'], staff=None)
                                    sale_item.meal=meal
                            elif dish:
                                if staff:
                                    # deduct_current_production_plan(request=request, meal=None, dish=dish.name, product=None, quantity=item['quantity'], staff=True)
                                    sale_item.dish=dish
                                else:
                                    # deduct_current_production_plan(request=request, meal=None, dish=dish.name, product=None, quantity=item['quantity'], staff=None)
                                    sale_item.dish=dish
                            
                            sale_item.save()

                            logger.info(f'Sale item saved: {sale_item}')
                            
                            def log(products, sale_item):
                                for product in products:
                                    ProductionLogs.objects.create(
                                        branch = request.user.branch,
                                        user=request.user, 
                                        action='sale',
                                        product=product,
                                        quantity=sale_item.quantity,
                                        total_quantity=product.quantity,
                                    )
                                    logger.info(f'Log for {sale_item}')
                                
                        else:
                            logger.info('Finished goods')
                            product_id = item['meal_id'].split('-')[1]
                            product = get_object_or_404(Product, id=product_id,branch = request.user.branch)
                            product.quantity -= item['quantity']

                            logger.info(f'finished product {product}')
                            if staff:
                                sale_item = SaleItem.objects.create(
                                    sale=sale,
                                    product=product,
                                    quantity=item['quantity'],
                                    price=0.00,
                                )
                                # deduct_current_production_plan(request=request, meal=None, dish=None, product=product.name, quantity=item['quantity'], staff=True)
                            else:
                                sale_item = SaleItem.objects.create(
                                    sale=sale,
                                    product=product,
                                    quantity=item['quantity'],
                                    price=product.price,
                                )
                                # deduct_current_production_plan(request=request, meal=None, dish=None, product=product.name, quantity=item['quantity'], staff=None)
                            logger.info(f'Saved sale item: {sale_item}')
                            
                            Logs.objects.create(
                                # branch = request.user.branch,
                                user=request.user, 
                                action='sale',
                                product=product,
                                quantity=sale_item.quantity,
                                total_quantity=product.quantity,
                            )

                            logger.info(f'log sale item: {sale_item}')

                            product.save()
                            logger.info(f'Saved product: {sale_item}')
                    if task_list:
                        logger.info(F'Update task list')
                        updateTakeAway.delay(task_list)
                    
                    CashBook.objects.create(
                        branch = request.user.branch,
                        sale=sale, 
                        amount=sale.total_amount,
                        debit=True,
                        description=f'Sale (Receipt number: {sale.receipt_number})'
                    )

                    logger.info('Cash book object created.')

                    # create change
                    if change_data:
                        logger.info(f'creating change object if change data exists')
                        
                        create_client_change(change_data, sale.receipt_number, sale.cashier, sale)

                    Logs.objects.create(
                        user=request.user, 
                        action='sale',
                        sale=sale,
                        quantity=sale_item.quantity,
                        total_quantity=sale_item.quantity,
                    )
                    
                    logger.info(f'Sale: {sale.id} Processed')

                    data = {
                        'receipt_number': sale.receipt_number,
                        'date': str(localdate()),
                        'time': timezone.localtime().strftime("%H:%M:%S"),
                        'cashier': f'{request.user.first_name} {request.user.last_name}',
                        'receipt_number': sale.receipt_number,
                        'total_amount': sale.total_amount,
                        'receipt_number':sale.receipt_number,
                        'tax': sale.tax,
                        'sub_total': sale.sub_total,
                        'received_amount': received_amount,
                        'change': received_amount - sale.total_amount,
                        'items': list(SaleItem.objects.filter(sale=sale).values('quantity', 'price', 'meal__name', 'dish__name', 'product__name'))
                    }

                    # total_sales = Sale.objects.filter(date=today).aggregate(total=Sum('total_amount'))['total'] or 0
                    # channel_layer = get_channel_layer()
                    # async_to_sync(channel_layer.group_send)(
                    #     "sales_group",
                    #     {
                    #         "type": "send_sales_update",
                    #         "data": {"total_sales": str(total_sales)},
                    #     }
                    # )

                    SyncLog.objects.create(
                        user=request.user,
                        operation=item['operation'],
                        model_name='Task',
                        object_id=item['id']
                    )
                    
        except Exception as e:
            SyncLog.objects.create(
                user=request.user,
                operation=item['operation'],
                model_name='Task',
                object_id=item['id'],
                success=False,
                error_message=str(e)
            )
            logger.error(f'Error syncing: {e}')
                
        return Response({
            'server_changes': SaleSerializer(server_changes, many=True).data,
            'conflicts': conflicts,
            'sync_timestamp': timezone.now().isoformat()
        })
        