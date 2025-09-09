import json
import os
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
import warnings
from decimal import Decimal
from users.models import Branch, Company
from finance.models import Sale, SaleItem, Change, CashierExpense, Meal, Dish, Product

# Ignore runtime warnings during tests
warnings.filterwarnings(
    "ignore",
    message="No directory at",
    module="whitenoise"
)

# Use test settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'test_settings'


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class AnalyticsViewsTestCase(TestCase):
    def setUp(self):
        """Create test client, test user, and initial analytics data."""
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

        # Create test data for analytics
        self.today = timezone.now().date()
        self.yesterday = self.today - timezone.timedelta(days=1)

        # Create test sale
        self.sale = Sale.objects.create(
            date=self.today,
            total_amount=Decimal('200.00'),
            branch=self.branch,
            void=False,
            staff=False
        )

        # Create test meal and dish
        self.meal = Meal.objects.create(name='Test Meal', price=Decimal('10.00'))
        self.dish = Dish.objects.create(name='Test Dish', price=Decimal('5.00'))

        # Create sale items
        self.sale_item = SaleItem.objects.create(
            sale=self.sale,
            meal=self.meal,
            quantity=2,
            price=Decimal('20.00')
        )

        # Create change record
        self.change = Change.objects.create(
            amount=Decimal('50.00'),
            branch=self.branch,
            collected=False,
            timestamp=timezone.now()
        )

        # Create cashier expense
        self.cashier_expense = CashierExpense.objects.create(
            date=self.today,
            amount=Decimal('25.00'),
            branch=self.branch
        )

    def test_analytics_index_view(self):
        """Test retrieving the analytics index view."""
        response = self.client.get(reverse('analytics_index'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertTemplateUsed(response, 'analytics.html')

    def test_analytics_view_hour_filter(self):
        """Test analytics view with hour filter."""
        response = self.client.get(
            reverse('analytics_overview'),
            {'filter_by': 'hour'},
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertIn('sales_by_hour', data)

    def test_analytics_view_day_filter(self):
        """Test analytics view with day filter."""
        response = self.client.get(
            reverse('analytics_overview'),
            {'filter_by': 'day'},
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertIn('today_sales', data)
            self.assertIn('yesterday_sales', data)

    def test_analytics_view_month_filter(self):
        """Test analytics view with month filter."""
        response = self.client.get(
            reverse('analytics_overview'),
            {'filter_by': 'month'},
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertIn('month_sales', data)

    def test_analytics_view_year_filter(self):
        """Test analytics view with year filter."""
        response = self.client.get(
            reverse('analytics_overview'),
            {'filter_by': 'year'},
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertIn('year_sales', data)

    def test_analysis_view(self):
        """Test the analysis view."""
        response = self.client.get(reverse('analysis'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertIn('success', data)

    def test_analysis_expenses_view(self):
        """Test the analysis expenses view."""
        response = self.client.get(reverse('analysis_expenses'), follow=True)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertIn('success', data)

    def test_analytics_view_no_data(self):
        """Test analytics view with no data."""
        # Delete all test data
        Sale.objects.all().delete()
        SaleItem.objects.all().delete()
        Change.objects.all().delete()

        response = self.client.get(
            reverse('analytics_overview'),
            {'filter_by': 'day'},
            follow=True
        )
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertEqual(data['today_sales'], 0)
            self.assertEqual(data['yesterday_sales'], 0)

    def test_analytics_view_unauthorized(self):
        """Test analytics view with non-admin user."""
        # Create non-admin user
        non_admin = User.objects.create_user(
            username='nonadmin',
            password='testpass123',
            role='staff',
            email='staff@test.com',
            branch=self.branch
        )

        self.client.force_login(non_admin)

        response = self.client.get(reverse('analytics_overview'), follow=True)
        # Should redirect or show unauthorized access
        # Adjust based on your admin_required decorator implementation
        self.assertNotEqual(response.status_code, 200)


if __name__ == "__main__":
    from django.test.utils import setup_test_environment

    setup_test_environment()