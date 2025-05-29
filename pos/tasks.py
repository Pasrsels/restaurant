from celery import shared_task
from datetime import datetime, time

@shared_task
def lowStockNotifications(dish_name, quantity):

    current_time = datetime.now().time()

    target_time_morning = time(11,59,59)
    target_time_afternoon = time(13,30,00)
    target_time_latenoon = time(16,30,00)
    target_time_evening = time(18,00,00)

    if current_time < target_time_morning:
        notify = f'{dish_name} is low current quantity is {quantity}'
