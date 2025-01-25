from django_celery_beat.models import PeriodicTask, IntervalSchedule
from .models import Budget
from django.utils import timezone
from datetime import timedelta

def create_periodic_task():
    budget_info = Budget.objects.all()

    for items in budget_info:
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=items.time,
            period=IntervalSchedule.WEEKS,
        )

        PeriodicTask.objects.create(
            interval=schedule,
            name=f"Run budget creation after:{schedule.every,schedule.period}",
            task="inventory.tasks.CreateBudgetTask",
            start_time=items.start_date + timedelta(days=7),
            kwargs=f"{{'budget_id':{items.id}}}",
        )
