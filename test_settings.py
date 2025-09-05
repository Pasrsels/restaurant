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
    ExpenseCategory, Expense, CashBook, CashierAccount, CashierExpense,
    Sale, COGS, CashUp, CashBookNote
)

# Ignore runtime warnings during tests
warnings.filterwarnings(
    "ignore",
    message="No directory at",
    module="whitenoise"
)

# Use test settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'test_settings'


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

        # Create a cashbook entry
        self.cashbook_entry = CashBook.objects.create(
            branch=self.branch,
            amount=Decimal('1000.00'),
            balance=Decimal('1000.00'),
            transaction_type='opening_balance',
            user=self.user
        )

        # Create a cashier account
        self.cashier_account = CashierAccount.objects.create(
            cashier=self.user,
            amount=Decimal('500.00'),
            branch=self.branch
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
            branch=self.branch
        )

        # Create cashup
        self.cashup = CashUp.objects.create(
            cashier=self.user,
            cashed_amount=Decimal('150.00'),
            sales=Decimal('200.00'),
            branch=self.branch,
            user=self.user
        )

    def test_expense_creation(self):
        """Test that expense was created in setup."""
        self.assertEqual(Expense.objects.count(), 1)
        self.assertEqual(Expense.objects.first().amount, Decimal('100.00'))

    def test_finance_home_view(self):
        """Test retrieving the finance home view."""
        response = self.client.get(reverse('finance:finance'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    @override_settings(DEBUG=True)
    def test_expenses_view_get(self):
        """Test retrieving the expenses view."""
        response = self.client.get(reverse('finance:expenses'), follow=True)
        self.assertIn(response.status_code, [200, 302])
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
        self.assertIn(response.status_code, [200, 302])
        # Check if the expense was created
        self.assertTrue(Expense.objects.filter(description="New Expense").exists())

    def test_get_expense_view(self):
        """Test retrieving details of a specific expense."""
        response = self.client.get(
            reverse('finance:get_expense', args=[self.expense.id]),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['data']['id'], self.expense.id)

    def test_add_expense_category_view(self):
        """Test adding a new expense category."""
        # Test GET request
        response = self.client.get(reverse('finance:add_expense_category'), follow=True)
        self.assertEqual(response.status_code, 200)

        # Test POST request
        data = {'name': 'New Category'}
        response = self.client.post(
            reverse('finance:add_expense_category'),
            data=json.dumps(data),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        # Check if the category was created
        self.assertTrue(ExpenseCategory.objects.filter(name="New Category").exists())

    def test_add_or_edit_expense_view(self):
        """Test adding or editing an expense."""
        data = {
            'amount': '200.00',
            'description': 'Edited Expense',
            'category': self.expense_category.id,
            'id': self.expense.id
        }
        response = self.client.post(
            reverse('finance:add_or_edit_expense'),
            data=json.dumps(data),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        # Verify the expense was updated
        updated_expense = Expense.objects.get(id=self.expense.id)
        self.assertEqual(updated_expense.amount, Decimal('200.00'))

    def test_delete_expense_view(self):
        """Test deleting an expense."""
        response = self.client.delete(
            reverse('finance:delete_expense', args=[self.expense.id]),
            follow=True
        )
        self.assertIn(response.status_code, [200, 204, 302])
        # Verify the expense was marked as canceled
        updated_expense = Expense.objects.get(id=self.expense.id)
        self.assertTrue(updated_expense.cancel)

    def test_update_expense_status_view(self):
        """Test updating expense status."""
        response = self.client.post(
            reverse('finance:update_expense_status'),
            data=json.dumps({'id': self.expense.id, 'status': True}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        # Verify the expense status was updated
        updated_expense = Expense.objects.get(id=self.expense.id)
        self.assertTrue(updated_expense.status)

    @override_settings(DEBUG=True)
    def test_cashbook_view_get(self):
        """Test retrieving the cashbook view."""
        response = self.client.get(reverse('finance:cashbook'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertIn('entries', response.context)

    def test_cashbook_note_view(self):
        """Test adding a note to cashbook."""
        response = self.client.post(
            reverse('finance:cashbook_note'),
            data=json.dumps({'entry_id': self.cashbook_entry.id, 'note': 'Test note'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_cashbook_note_detail_view(self):
        """Test viewing a specific cashbook note."""
        # First add a note
        CashBookNote.objects.create(
            entry=self.cashbook_entry,
            user=self.user,
            note='Test note'
        )

        response = self.client.get(
            reverse('finance:cashbook_note_view', args=[self.cashbook_entry.id]),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])

    def test_download_cashbook_report(self):
        """Test downloading cashbook report."""
        response = self.client.get(reverse('finance:download_cashbook_report'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cancel_transaction_view(self):
        """Test canceling a transaction."""
        response = self.client.post(
            reverse('finance:cancel-entry'),
            data=json.dumps({'entry_id': self.cashbook_entry.id}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        # Verify the transaction was canceled
        updated_entry = CashBook.objects.get(id=self.cashbook_entry.id)
        self.assertTrue(updated_entry.cancelled)

    def test_update_transaction_status_view(self):
        """Test updating transaction status."""
        response = self.client.post(
            reverse('finance:update_transaction_status', args=[self.cashbook_entry.id]),
            data=json.dumps({'status': True, 'field': 'manager'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        # Verify the transaction status was updated
        updated_entry = CashBook.objects.get(id=self.cashbook_entry.id)
        self.assertTrue(updated_entry.manager)

    def test_cogs_list_view(self):
        """Test retrieving COGS list."""
        response = self.client.get(reverse('finance:cogs'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertIn('cogs', response.context)

    def test_cashiers_list_view(self):
        """Test retrieving cashiers list."""
        response = self.client.get(reverse('finance:cashiers_list'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertIn('cashiers', response.context)

    def test_generate_report_view(self):
        """Test generating a financial report."""
        response = self.client.get(reverse('finance:generate_report'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cash_up_view(self):
        """Test processing a cash-up transaction."""
        # Test GET request
        response = self.client.get(reverse('finance:cash_up'), follow=True)
        self.assertIn(response.status_code, [200, 302])

        # Test POST request
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
        self.assertIn(response.status_code, [200, 302])

    def test_claim_cashup_view(self):
        """Test claiming a cashup difference."""
        response = self.client.post(
            reverse('finance:claim-cashup', args=[self.cashup.id]),
            data=json.dumps({'cashup_id': self.cashup.id, 'claim_amount': '50.00'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_charge_cashup_difference_view(self):
        """Test charging cashup difference."""
        response = self.client.post(
            reverse('finance:charge_cashup_difference'),
            data=json.dumps({'cashup_id': self.cashup.id, 'charge_amount': '50.00'}),
            content_type='application/json',
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])

    def test_days_data_view(self):
        """Test retrieving daily sales data."""
        response = self.client.get(reverse('finance:days_data'), follow=True)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIsInstance(response_data, dict)

    def test_transaction_logs_view(self):
        """Test retrieving transaction logs."""
        response = self.client.get(reverse('finance:logs'), follow=True)
        self.assertIn(response.status_code, [200, 302])

    def test_cashier_expenses_view(self):
        """Test retrieving cashier expenses."""
        response = self.client.get(
            reverse('finance:cashier_expenses', args=[self.user.id]),
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertIn('grouped_expenses', response.context)

    def test_pl_overview_view(self):
        """Test retrieving profit/loss overview."""
        response = self.client.get(reverse('finance:pl_overview'), {'filter': 'today'}, follow=True)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIn('net_profit', response_data)

    def test_income_json_endpoint(self):
        """Test retrieving income data."""
        response = self.client.get(reverse('finance:income_json'), follow=True)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIn('sales_total', response_data)

    def test_expense_json_endpoint(self):
        """Test retrieving expenses data."""
        response = self.client.get(reverse('finance:expense_json'), follow=True)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIn('expense_total', response_data)

    def test_income_graph_view(self):
        """Test retrieving income graph data."""
        response = self.client.get(reverse('finance:income_graph'), follow=True)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIsInstance(response_data, dict)

    def test_expense_graph_view(self):
        """Test retrieving expense graph data."""
        response = self.client.get(reverse('finance:expense_graph'), follow=True)
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertIsInstance(response_data, dict)

    def test_sale_view(self):
        """Test retrieving sales view."""
        response = self.client.get(reverse('finance:sales'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertIn('sales', response.context)


if __name__ == "__main__":
    from django.test.utils import setup_test_environment

    setup_test_environment()