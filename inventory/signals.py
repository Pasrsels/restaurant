from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import Product, InventoryNotificationLog
from loguru import logger
from settings.models import EmailNotifications

def send_notification_email(subject, message, action_type):
    """
        Send email to all users subscribed to this action type.
    """
    # recipients = list(
    #     EmailNotifications.objects.filter(
    #         is_active=True, notification_type=action_type
    #     ).values_list('email', flat=True)
    # )
    
    recipients = ['cassymyo@gmail.com']

    if recipients:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )

@receiver(post_save, sender=Product)
def inventory_create_update_notification(sender, instance, created, **kwargs):
    """
        Handle notifications for CREATE and UPDATE actions.
    """
    if created:
        action_type = 'create'
        subject = f"New Product Added: {instance.name}"
        message = (
            f"A new product '{instance.name}' was added to the inventory.\n"
            f"Quantity: {instance.quantity}"
        )
        logger.success(f'Email succesfully send for product creation: {instance.name}')
        
        InventoryNotificationLog.objects.create(
            inventory_item=instance,
            action_type=action_type,
            message=message
        )
        send_notification_email(subject, message, action_type)
    else: pass
        # action_type = 'update'
        # subject = f"Product Updated: {instance.name}"
        # message = (
        #     f"The product '{instance.name}' was updated.\n"
        #     f"New Quantity: {instance.quantity}\n"
        #     f"Last Updated: {instance.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"
        # )
        
        # logger.success(f'Email succesfully send for product update: {instance.name}')
        

@receiver(post_delete, sender=Product)
def inventory_delete_notification(sender, instance, **kwargs):
    """
        Handle notifications for DELETE action.
    """
    action_type = 'delete'
    subject = f"Product Deleted: {instance.product_name}"
    message = (
        f"The product '{instance.name}' was removed from inventory.\n"
        f"Last known quantity: {instance.quantity}"
    )

    InventoryNotificationLog.objects.create(
        inventory_item=instance,
        action_type=action_type,
        message=message
    )

    send_notification_email(subject, message, action_type)
