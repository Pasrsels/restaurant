import json
import os
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
import warnings
from decimal import Decimal
from users.models import Branch, Company
from finance.models import (
    ExpenseCategory, Expense, CashBook, CashierAccount, CashierExpense, Sale, COGS, CashUp
)

# Ignore runtime warnings during tests
warnings.filterwarnings(
    "ignore",
    message="No directory at",
    module="whitenoise"
)

# Use test settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'test_settings'


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class FinanceViewsTestCase(TestCase):
    def setUp(self):
        """Create test client, test user, and initial finance data."""
        self.client = Client()
        User = get_user_model()

        # Create company if it doesn't exist
        self.company = Company.objects.first()
        if not self.company:
            self.company = Company.objects.create(name='Test Company')

        self.branch = Branch.objects.create(
            branch_name="Test Branch",
            company=self.company
        )

        self.user = User.objects.create_user(
            username='adminuser',
            password='adminpass',
            role='admin',
            email='admin@test.com',
            branch=self.branch
        )
        self.client.force_login(self.user)

        self.expense_category = ExpenseCategory.objects.create(name="Utilities")
        self.expense = Expense.objects.create(
            branch=self.branch,
            category=self.expense_category,
            amount=Decimal('100.00'),
            user=self.user,
            description="Test Expense"
        )

        # ✅ FIX: Create corresponding CashBook entry for the expense
        self.cashbook_expense = CashBook.objects.create(
            branch=self.branch,
            expense=self.expense,
            amount=self.expense.amount,
            credit=True,
            description="Initial Expense"
        )

        # Create a cashbook entry
        self.cashbook_entry = CashBook.objects.create(
            branch=self.branch,
            amount=Decimal('1000.00')
        )

        # Create a cashier account
        self.cashier_account = CashierAccount.objects.create(
            cashier=self.user,
            amount=Decimal('500.00'),
        )

        # Create a cashier expense
        self.cashier_expense = CashierExpense.objects.create(
            cashier=self.user,
            amount=Decimal('50.00'),
            description="Test Expense",
            branch=self.branch
        )

        # Create a sale
        self.sale = Sale.objects.create(
            total_amount=Decimal('200.00'),
            branch=self.branch,
            void=False,
            cashier=self.user
        )

        # Create COGS
        self.cogs = COGS.objects.create(
            amount=Decimal('80.00'),
        )

        # Create cashup
        self.cashup = CashUp.objects.create(
            cashier=self.user,
            cashed_amount=Decimal('150.00'),
            sales=Decimal('200.00'),
            branch=self.branch,
            user=self.user
        )

    # --- All tests remain unchanged ---
    def test_expense_creation(self):
        """Test that expense was created in setup."""
        self.assertEqual(Expense.objects.count(), 1)
        self.assertEqual(Expense.objects.first().amount, Decimal('100.00'))

    def test_finance_home_view(self):
        """Test retrieving the finance home view."""
        response = self.client.get(reverse('finance:finance'), follow=True)
        self.assertIn(response.status_code, [200, 201, 302])

    @override_settings(DEBUG=True)
    def test_expenses_view_get(self):
        """Test retrieving the expenses view."""
        response = self.client.get(reverse('finance:expenses'), follow=True)
        self.assertIn(response.status_code, [200, 201, 302])
        if response.status_code == 200:
            self.assertIn('expenses', response.context)

    def test_expenses_view_post(self):
        """Test creating a new expense."""
        data = {
            'amount': '150.00',
            'description': 'New Expense',
            'category': self.expense_category.id,
        }
        response = self.client.post(
            reverse('finance:expenses'),
            data=json.dumps(data),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(Expense.objects.filter(description="New Expense").exists())

    def test_get_expense_view(self):
        """Test retrieving details of a specific expense."""
        response = self.client.get(
            reverse('finance:get_expense', args=[self.expense.id]),
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_add_expense_category_view(self):
        """Test adding a new expense category."""
        data = {'name': 'New Category'}
        response = self.client.post(
            reverse('finance:add_expense_category'),
            data=json.dumps(data),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(ExpenseCategory.objects.filter(name="New Category").exists())

    def test_add_or_edit_expense_view(self):
        """Test editing an existing expense (requires id)."""
        data = {
            'id': self.expense.id,
            'amount': 200.00,
            'description': 'Edited Expense',
            'category': self.expense_category.id,
        }
        response = self.client.post(
            reverse('finance:add_or_edit_expense'),
            data=json.dumps(data),
            content_type='application/json',
            follow=True
        )
        print(response.content)
        self.assertIn(response.status_code, [200, 201, 302])
        self.expense.refresh_from_db()
        self.assertEqual(float(self.expense.amount), 200.00)
        self.assertEqual(self.expense.description, 'Edited Expense')

    # --- Remaining tests unchanged ---
    def test_delete_expense_view(self):
        response = self.client.delete(
            reverse('finance:delete_expense', args=[self.expense.id]),
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_update_expense_status_view(self):
        response = self.client.post(
            reverse('finance:update_expense_status'),
            data=json.dumps({'id': self.expense.id, 'status': True}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    @override_settings(DEBUG=True)
    def test_cashbook_view_get(self):
        response = self.client.get(reverse('finance:cashbook'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cashbook_note_view(self):
        response = self.client.post(
            reverse('finance:cashbook_note'),
            data=json.dumps({'entry_id': self.cashbook_entry.id, 'note': 'Test note'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])

    def test_cashbook_note_detail_view(self):
        response = self.client.get(
            reverse('finance:cashbook_note_view', args=[self.cashbook_entry.id]),
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_download_cashbook_report(self):
        response = self.client.get(reverse('finance:download_cashbook_report'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cancel_transaction_view(self):
        response = self.client.post(
            reverse('finance:cancel-entry'),
            data=json.dumps({'entry_id': self.cashbook_entry.id}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])

    def test_update_transaction_status_view(self):
        response = self.client.post(
            reverse('finance:update_transaction_status', args=[self.cashbook_entry.id]),
            data=json.dumps({'status': True, 'field': 'manager'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_cogs_list_view(self):
        response = self.client.get(reverse('finance:cogs'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cashiers_list_view(self):
        response = self.client.get(reverse('finance:cashiers_list'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_generate_report_view(self):
        response = self.client.get(reverse('finance:generate_report'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cash_up_view(self):
        data = {
            'cashed_amount': '200.00',
            'cashier': self.user.id,
        }
        response = self.client.post(
            reverse('finance:cash_up'),
            data=json.dumps(data),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])

    def test_claim_cashup_view(self):
        response = self.client.post(
            reverse('finance:claim-cashup', args=[self.cashup.id]),
            data=json.dumps({'cashup_id': self.cashup.id, 'claim_amount': '50.00'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])

    def test_charge_cashup_difference_view(self):
        response = self.client.post(
            reverse('finance:charge_cashup_difference'),
            data=json.dumps({'cashup_id': self.cashup.id, 'charge_amount': '50.00'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 201, 302])

    def test_days_data_view(self):
        response = self.client.get(reverse('finance:days_data'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_transaction_logs_view(self):
        response = self.client.get(reverse('finance:logs'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cashier_expenses_view(self):
        response = self.client.get(
            reverse('finance:cashier_expenses', args=[self.user.id]),
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_pl_overview_view(self):
        response = self.client.get(reverse('finance:pl_overview'), {'filter': 'today'}, follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_income_json_endpoint(self):
        response = self.client.get(reverse('finance:income_json'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_expense_json_endpoint(self):
        response = self.client.get(reverse('finance:expense_json'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_income_graph_view(self):
        response = self.client.get(reverse('finance:income_graph'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_expense_graph_view(self):
        response = self.client.get(reverse('finance:expense_graph'), follow=True)
        self.assertIn(response.status_code, [200, 302])


if __name__ == "__main__":
    from django.test.utils import setup_test_environment
    setup_test_environment()
