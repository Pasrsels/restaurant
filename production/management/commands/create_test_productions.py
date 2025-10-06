# production/management/commands/create_test_productions.py
import random
import uuid
from django.core.management.base import BaseCommand
from django.utils import timezone
from production.models import Production
from users.models import Branch

class Command(BaseCommand):
    help = "Create 20 test Production plans"

    def handle(self, *args, **kwargs):
        branch, _ = Branch.objects.get_or_create(branch_sname="Test")

        for _ in range(20):
            plan = Production.objects.create(
                branch=branch,
                confirm=random.choice([True, False]),
                declared=random.choice([True, False]),
                plan_number=f"PP-{uuid.uuid4().hex[:5].upper()}",
            )
            self.stdout.write(self.style.SUCCESS(f"Created {plan.plan_number}"))

        self.stdout.write(self.style.SUCCESS("✅ Successfully created 20 test Production plans."))
