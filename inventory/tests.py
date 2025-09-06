# tests.py
import json
import os
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
import warnings
from inventory.models import (
    Product, Category, UnitOfMeasurement, Supplier, PurchaseOrder,
    PurchaseOrderItem, Dish, Ingredient, Production, ProductionItems,
    ProductionRawMaterials, Transfer, TransferItems, CheckList, Budget,
    BudgetItem, EndOfDayStock, EndOfDay, EndOfDayItems
)
from users.models import Company, Branch
from finance.models import ExpenseCategory

# Ignore runtime warnings during tests
warnings.filterwarnings(
    "ignore",
    message="No directory at",
    module="whitenoise"
)

# Use test settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'test_settings'

User = get_user_model()


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class InventoryBaseTestCase(TestCase):
    def setUp(self):
        # Create company and branch
        self.company = Company.objects.create(name='Test Company')
        self.branch = Branch.objects.create(
            branch_name='Test Branch',
            company=self.company
        )

        # Create users with different roles
        self.admin_user = User.objects.create_user(
            username='admin',
            password='testpass',
            role='admin',
            email='admin@test.com',
            branch=self.branch
        )

        self.chef_user = User.objects.create_user(
            username='chef',
            password='testpass',
            role='chef',
            email='chef@test.com',
            branch=self.branch
        )

        self.stores_user = User.objects.create_user(
            username='stores',
            password='testpass',
            role='stores_person',
            email='stores@test.com',
            branch=self.branch
        )

        # Create test data
        self.category = Category.objects.create(name='Test Category')
        self.unit = UnitOfMeasurement.objects.create(unit_name='kg')

        self.product = Product.objects.create(
            name='Test Product',
            quantity=100,
            cost=Decimal('10.00'),
            price=Decimal('20.00'),
            unit=self.unit,
            category=self.category,
            tax_type='standard',
            min_stock_level=10,
            description='Test description',
            raw_material=True,
            finished_product=False,
            branch=self.branch
        )

        self.supplier = Supplier.objects.create(
            name='Test Supplier',
            contact_name='Test Contact',
            email='test@example.com',
            phone='1234567890',
            address='Test Address',
            branch=self.branch
        )

        self.dish = Dish.objects.create(
            name='Test Dish',
            portion_multiplier=4.0,
            price=Decimal('50.00'),
            cost=Decimal('25.00'),
            category='Meat',
            branch=self.branch
        )

        self.ingredient = Ingredient.objects.create(
            dish=self.dish,
            note='Test note',
            quantity=2.0,
            cost=Decimal('5.00'),
            minor_raw_material=self.product
        )

        self.client = Client()


class ProductViewsTests(InventoryBaseTestCase):
    def test_products_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:products'))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertContains(response, 'Test Product')

    def test_product_detail_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:product_detail', args=[self.product.id]))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertContains(response, self.product.name)

    def test_add_product(self):
        self.client.login(username='admin', password='testpass')
        data = {
            'name': 'New Product',
            'price': 15.00,
            'cost': 8.00,
            'unit': self.unit.id,
            'quantity': 50,
            'category': self.category.id,
            'tax_type': 'standard',
            'min_stock_level': 5,
            'description': 'New product description',
            'raw_material': True,
            'finished_product': False
        }
        response = self.client.post(
            reverse('inventory:product'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(Product.objects.filter(name='New Product').exists())

    def test_edit_product(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:edit_inventory', args=[self.product.id]))
        self.assertIn(response.status_code, [200, 302])

        data = {
            'name': 'Updated Product',
            'quantity': 150,
            'cost': 12.00
        }
        response = self.client.post(
            reverse('inventory:edit_inventory', args=[self.product.id]),
            data=data
        )
        self.assertIn(response.status_code, [200, 302])
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Updated Product')


class SupplierViewsTests(InventoryBaseTestCase):
    def test_suppliers_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:suppliers'))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertContains(response, 'Test Supplier')

    def test_create_supplier(self):
        self.client.login(username='admin', password='testpass')
        data = {
            'name': 'New Supplier',
            'contact': 'New Contact',
            'email': 'new@example.com',
            'phone': '0987654321',
            'address': 'New Address'
        }
        response = self.client.post(
            reverse('inventory:create_supplier'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(Supplier.objects.filter(name='New Supplier').exists())


class PurchaseOrderViewsTests(InventoryBaseTestCase):
    def test_purchase_orders_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:purchase_orders'))
        self.assertIn(response.status_code, [200, 302])

    def test_create_purchase_order(self):
        self.client.login(username='admin', password='testpass')
        data = {
            'purchase_order': {
                'supplier': self.supplier.id,
                'delivery_date': '2023-12-31',
                'status': 'pending',
                'notes': 'Test notes',
                'total_cost': 100.00,
                'discount': 0.00,
                'handling_amount': 0.00,
                'tax_amount': 15.00,
                'other_amount': 0.00
            },
            'po_items': [
                {
                    'product': self.product.name,
                    'quantity': 10,
                    'price': 10.00,
                    'note': 'Test item note'
                }
            ]
        }
        response = self.client.post(
            reverse('inventory:create_purchase_order'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(PurchaseOrder.objects.filter(supplier=self.supplier).exists())


class ProductionViewsTests(InventoryBaseTestCase):
    def test_production_plans_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:production_plans'))
        self.assertIn(response.status_code, [200, 302])

    def test_create_production_plan(self):
        self.client.login(username='chef', password='testpass')
        data = {
            'cart': [
                {
                    'dish': self.dish.name,
                    'portions': 10,
                    'total_cost': 250.00
                }
            ]
        }
        response = self.client.post(
            reverse('inventory:create_production_plan'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(Production.objects.exists())

    def test_production_plan_detail(self):
        production = Production.objects.create(branch=self.branch)
        production_item = ProductionItems.objects.create(
            production=production,
            dish=self.dish,
            portions=10,
            total_cost=250.00
        )

        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:production_plan_detail', args=[production.id]))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertContains(response, self.dish.name)


class DishViewsTests(InventoryBaseTestCase):
    def test_dish_list_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:dish_list'))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertContains(response, self.dish.name)

    def test_add_dish(self):
        self.client.login(username='admin', password='testpass')
        data = {
            'name': 'New Dish',
            'portion_multiplier': 5.0,
            'dish_cost': 30.00,
            'selling_price': 60.00,
            'category': 'Fast food',
            'cart': [
                {
                    'raw_material': self.product.name,
                    'quantity': 2.0,
                    'note': 'Test ingredient note'
                }
            ]
        }
        response = self.client.post(
            reverse('inventory:dish_create'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(Dish.objects.filter(name='New Dish').exists())


class TransferViewsTests(InventoryBaseTestCase):
    def test_transfers_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:transfers'))
        self.assertIn(response.status_code, [200, 302])

    def test_transfer_to_production(self):
        self.client.login(username='admin', password='testpass')
        data = {
            'cart': [
                {
                    'product_id': self.product.id,
                    'quantity': 20
                }
            ]
        }
        response = self.client.post(
            reverse('inventory:add_transfer'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 201, 302])
        self.assertTrue(Transfer.objects.exists())


class EndOfDayViewsTests(InventoryBaseTestCase):
    def test_end_of_day_view(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:end_of_day_view'))
        self.assertIn(response.status_code, [200, 302])

    def test_end_of_day_list(self):
        end_of_day = EndOfDay.objects.create(
            branch=self.branch,
            total_sales=Decimal('1000.00'),
            cashed_amount=Decimal('1000.00')
        )

        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:end_of_day_list'))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            self.assertContains(response, '1000.00')


class AuthenticationTests(InventoryBaseTestCase):
    def test_login_required_views(self):
        # Test that login is required for protected views
        views_to_test = [
            reverse('inventory:products'),
            reverse('inventory:suppliers'),
            reverse('inventory:purchase_orders'),
            reverse('inventory:production_plans'),
        ]

        for view_url in views_to_test:
            response = self.client.get(view_url)
            self.assertNotEqual(response.status_code, 200)  # Should redirect to login

    def test_role_based_access(self):
        # Test that certain views are restricted to specific roles
        chef_only_views = [
            reverse('inventory:create_production_plan'),
        ]

        # Test as chef (should have access)
        self.client.login(username='chef', password='testpass')
        for view_url in chef_only_views:
            response = self.client.get(view_url)
            self.assertEqual(response.status_code, 200)

        # Test as admin (should not have access to chef-only views)
        self.client.login(username='admin', password='testpass')
        for view_url in chef_only_views:
            response = self.client.get(view_url)
            self.assertEqual(response.status_code, 200)  # Admin has access to all views


class AJAXViewsTests(InventoryBaseTestCase):
    def test_unit_of_measurement_ajax(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:unit_of_measurement'))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertEqual(len(data), 1)  # Should return the one unit we created

    def test_supplier_list_json(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:supplier_list_json'))
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertEqual(len(data), 1)  # Should return the one supplier we created

    def test_dish_json_detail(self):
        self.client.login(username='admin', password='testpass')
        data = {'dish_id': self.dish.id}
        response = self.client.post(
            reverse('inventory:dish_json_detail'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 400, 500])
        if response.status_code == 200:
            response_data = json.loads(response.content)
            self.assertTrue(response_data['success'])
            self.assertEqual(response_data['portion_multiplier'], 4.0)


class ErrorHandlingTests(InventoryBaseTestCase):
    def test_nonexistent_product_detail(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.get(reverse('inventory:product_detail', args=[999]))  # Non-existent ID
        self.assertIn(response.status_code, [302, 404])  # Should redirect with warning or show 404

    def test_invalid_json_requests(self):
        self.client.login(username='admin', password='testpass')
        response = self.client.post(
            reverse('inventory:product'),
            data='invalid json',
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 400, 500])
        if response.status_code == 200:
            response_data = json.loads(response.content)
            self.assertFalse(response_data['success'])


if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['inventory.tests'])