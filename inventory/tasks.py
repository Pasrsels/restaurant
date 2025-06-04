from utils.email import EmailThread
from . models import (
    Production, 
    Transfer,
    Supplier,
    PurchaseOrderItem,
    Product,
    Budget,
    BudgetItem,
    Dish,
    Ingredient
)
from django.core.mail import EmailMessage
from utils.supplier_best_price import best_price
from loguru import logger
from settings.models import NotificationEmails
from utils.email_notification import modules_list
from celery import shared_task
from decimal import Decimal
from django.core.mail import send_mail

@shared_task
def sendProductHistory(product_list):
    try:
        logger.info(product_list)

        for product in product_list:
            report = f"""
                Please find the stock movement below:
                Product Name: {product.get('Product_Name')} \n
                Opening Stock: {product.get('Start')} \n
                Stock In: {product.get('Stock')} \n
                Sold: {product.get('Sold')} \n
                Remaining: {product.get('Current')} \n
            """

            recipients = ['cassymyo@gmail.com', 'teddychinomona@gmail.com', 'mirackletec@gmail.com']

            subject = f"End of Day {product.get('Product_Name')} Report:"

            logger.info('Sending Email')
            mail = EmailMessage(
                subject=subject,
                body=report,
                # from_email='admin@techcity.co.zw',
                to=recipients,
            )

            mail.send()
            logger.info('Email sent successfully.')
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

@shared_task
def inventory_task(product_id):
    ingridients = Ingredient.objects.filter(minor_raw_material__id = product_id).all()
    product = Product.objects.get(id = product_id)
    new_cost = product.cost

    """
        dishes: list of all dishes that have the product
        concerned with the cost of the dish
    """

    for ingr in ingridients:
        logger.info(ingr)
        new_cost_per_unit = new_cost / Decimal(ingr.dish.portion_multiplier)
        ingr.dish.cost = (ingr.dish.cost - ingr.cost) + new_cost_per_unit
        ingr.dish.save()
        logger.info(f"Updated cost for dish: {ingr.dish.name} with cost: {ingr.dish.cost}")
    
        # Prepare email content
        subject = f"Updated Dish Cost: {ingr.dish.name}"
        message = f"""
        Hello,

        The cost of the dish {ingr.dish.name} has been updated.

        New Cost: {ingr.dish.cost:.2f}
        Change triggered by update to ingredient: {product.name}
        New cost per unit for this ingredient: {new_cost_per_unit:.2f}

        Regards,
        Urban Eats Inventory System
        """

        # Get recipients configured for dish cost update notifications
        # emails = NotificationEmails.objects.filter(module=modules_list["dish_cost_update"]).values_list("email", flat=True)
        emails = ['teddychinomona@gmail.com', 'cassymyo@gmail.com', 'mirackletec@gmail.com']

        if emails:
            send_email_task.delay(
                subject=subject,
                message=message,
                recipient_list=emails,
                from_email='admin@techcity.co.zw'  
            )
            logger.info(f"Email task queued for dish cost update: {ingr.dish.name}")
        else:
            logger.warning("No email recipients found for dish cost update notifications.")
    # for items in dish_ingredient_infor:
    #     print(items.dish.name)
    #     print(items.minor_raw_material)
    #     print(current_dish_name)
    #     if items.dish.name == current_dish_name or current_dish_name == None:
    #         print(f"Name:{items.minor_raw_material.name} Cost:{items.minor_raw_material.cost}")
    #         quantity = Decimal(str(items.quantity))
    #         portion = Decimal(str(items.dish.portion_multiplier))
    #         cost = items.minor_raw_material.cost

    #         Quantity_of_single = (Decimal(1) / portion) * quantity
    #         cost_of_single = Decimal(Quantity_of_single / quantity) * cost
            
    #         new_total_dish_cost += cost_of_single
    #         if current_dish_name == None:
    #             current_dish_name = items.dish.name
    #     else:
    #         print("Not current dish anymore")
    #         if current_dish_name:
    #             print(f"Updating cost for dish: {current_dish_name} with cost: {new_total_dish_cost}")
    #             dish_cost_update = Dish.objects.get(name = current_dish_name)
    #             dish_cost_update.cost = new_total_dish_cost
    #             dish_cost_update.save()
    #         current_dish_name = items.dish.name
    #         new_total_dish_cost = 0
    #         quantity = Decimal(str(items.quantity))
    #         portion = Decimal(str(items.dish.portion_multiplier))
    #         cost = items.minor_raw_material.cost

    #         Quantity_of_single = (Decimal(1) / portion) * quantity
    #         cost_of_single = Decimal(Quantity_of_single / quantity) * cost
            
    #         new_total_dish_cost += cost_of_single
    #         # if current_dish_name is not None:
    #         #     print(f"Updating cost for dish: {current_dish_name} with cost: {new_total_dish_cost}")
    #         #     dish_cost_update = Dish.objects.get(id=items.dish.id)
    #         #     dish_cost_update.cost = new_total_dish_cost
    #         #     dish_cost_update.save()

    #         # Now set for the current dish
    #         # current_dish_name = items.dish.name
    #         # new_total_dish_cost = 0

    # if current_dish_name:
    #     print(f"Final update for dish: {current_dish_name} with cost: {new_total_dish_cost}")
    #     last_dish = Dish.objects.get(name=current_dish_name)
    #     last_dish.cost = new_total_dish_cost
    #     last_dish.save()

    
    #when done
    print('Task done')
    # print(product)
    # dish_filtered_product = Ingredient.objects.filter(minor_raw_material__id = product_id).select_related('dish', 'minor_raw_material')
    # print(dish_filtered_product)
    # dishes_changed = []
    # for items in dish_filtered_product:
    #     print(items.dish.name)
    #     if dishes_changed:
    #         for item in dishes_changed:
    #             if item['Name'] == items.dish.name:
    #                 pass
    #             else:
    #                 print("here")
    #                 dishes_changed.append({'Name': items.dish.name})
    #     else:
    #         dishes_changed.append({'Name': items.dish.name})
    #     print(dishes_changed)
    #     email = EmailMessage(
    #         subject="Changed dishes",
    #         body=f"The list of dishes has been updated: {items.minor_raw_material.name}",
    #         from_email="admin@techcity.co.zw",
    #         to=["teddychinomona@gmail.com"],
    #     )
    #     email.send()
    return "Done"

@shared_task(bind=True, max_retries=3)
def send_email_task(self, subject, message, recipient_list, from_email=None):
    """
    A separate task for sending emails with retry logic
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )

        return f"Email sent to {', '.join(recipient_list)}"
    except Exception as exc:
        logger.warning(f"Email sending failed: {exc}. Retrying in 5 seconds...")
        # Retry after 5 seconds
        raise self.retry(exc=exc, countdown=5)


# def send_end_of_day_report(buffer):
#     email = EmailMessage(
#         f"End of Day Report:",
#         "Please find the attached End of Day report. The expected amount is to be calculated on cost price, since they are no stipulated prices per dishes, but if they to be put the expected table will be relavant.",
#         'admin@techcity.co.zw',
#         ['mirackletec@gmail.com'],
#     )
#     email.attach(f'EndOfDayReport.pdf', buffer.getvalue(), 'application/pdf')
    
#     EmailThread(email).start()

#     logger.info(f' End of day report email sent.')
 

def send_production_creation_notification(production_id):
    production = Production.objects.get(id=production_id)
    
    email = EmailMessage(
        subject=f"Production Plan Creation",
        body=f"""
        The email is to notify you on the creation of a Production Plan {production.production_plan_number}, and it requires your cornifimation.
        """,
        from_email='admin@techcity.co.zw',
        to=['cassymyo@gmail.com', 'teddychinomona@gmail.com', 'mirackletec@gmail.com'],
    )
    
    EmailThread(email).start()
    logger.info(f'Production confirmation ({production.production_plan_number}) sent.')
    

def transfer_notification(transfer_id):
    transfer = Transfer.objects.get(id=transfer_id)
    
    email = EmailMessage(
        subject="Raw Material Transfer Notification",
        body=f"""
        This is to notify you of a raw material transfer with the number {transfer.transfer_number}. 
        Please confirm receipt of this transfer.
        """,
        from_email='admin@techcity.co.zw',
        to=['mirackletec@gmail.com'],
    )
    
    EmailThread(email).start()
    
    logger.info(f'Notification for transfer {transfer.transfer_number} sent.')

def supplier_email(supplier_id, purchase_order_item):
    purchase_order_items = PurchaseOrderItem.objects.filter(purchase_order=purchase_order_item.purchase_order)
    supplier = Supplier.objects.get(id=supplier_id)

    price_list = [ sup['price'] for sup in best_price(purchase_order_item.product.name)]

    min_price = min(price_list)

    def send_email(purchase_order_item):
        logger.info(modules_list('Inventory'))
        email = EmailMessage(
            subject="Purchase Order Supplier notification",
            body=f"""
            This email is to notify you of a Supplier: {supplier.name} with a unit price of {po_item.unit_cost},
            Has been used for purchasing: {purchase_order_item.product.name}(s). 
            """,
            from_email='admin@techcity.co.zw',
            to=modules_list('Inventory'),
        )
        
        EmailThread(email).start()

        logger.info(f'Purchase order supplier notification email sent.')
    
    for po_item in purchase_order_items:  
        logger.info(po_item)
        if po_item.unit_cost > min_price and po_item.unit_cost not in price_list:
            logger.info('here')
            send_email(purchase_order_item)


def CreateBudgetTask(budget_id):
    budget_info = Budget.objects.get(id = budget_id)
    budget_item_info = BudgetItem.objects.filter(budget__id = budget_id).select_related('product', 'budget')

    budget_create = Budget.objects.create(
        name = budget_info.name,
        total_amount = budget_info.total_amount,
        description = budget_info.description,
        confirmation = False,
        user = budget_info.user
    )

    budget_items_list = []
    for items in budget_item_info:
        prod_info = Product.objects.get(id = items.product.id)
        budget_items_list.append(
            BudgetItem(
                budget = budget_create,
                product = prod_info,
                quantity = items.quantity,
                allocated_amount = items.allocated_amount,
                spent_amount = items.spent_amount,
            )
        )
    BudgetItem.objects.bulk_create(budget_items_list)
