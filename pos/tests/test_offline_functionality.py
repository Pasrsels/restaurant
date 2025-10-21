from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from inventory.models import Product, Category
from finance.models import Sale
import json

User = get_user_model()

class OfflineFunctionalityTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            is_active=True,
            is_staff=True
        )
        
        # Create test category
        self.category = Category.objects.create(name='Test Category')
        
        # Create test product
        self.product = Product.objects.create(
            name='Test Product',
            price=10.99,
            cost=5.99,
            quantity=100,
            category=self.category,
            branch=self.user.branch
        )
        
        # Set up the test client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Clear cache before each test
        cache.clear()
    
    def test_product_list_caching(self):
        """Test that product list is properly cached"""
        url = reverse('product-list')
        
        # First request should hit the database
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)  # Should return our test product
        
        # Delete the product from the database
        self.product.delete()
        
        # Second request should return cached data
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)  # Still returns the cached product
    
    def test_offline_order_creation(self):
        """Test creating an order while offline"""
        url = reverse('order-list')
        order_data = {
            'offline_id': 'test-offline-123',
            'customer_name': 'Test Customer',
            'payment_method': 'cash',
            'items': [
                {
                    'product': self.product.id,
                    'quantity': 2,
                    'unit_price': '10.99',
                    'total_price': '21.98',
                    'discount': '0.00',
                    'tax_amount': '3.30',
                    'notes': 'Test order'
                }
            ],
            'subtotal': '21.98',
            'tax_amount': '3.30',
            'discount_amount': '0.00',
            'total_amount': '25.28',
            'payment_status': 'completed',
            'status': 'completed'
        }
        
        # Create order
        response = self.client.post(
            url,
            data=json.dumps(order_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Sale.objects.count(), 1)
        
        # Verify the order was created with the correct data
        order = Sale.objects.first()
        self.assertEqual(order.customer_name, 'Test Customer')
        self.assertEqual(order.total_amount, 25.28)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().product, self.product)
    
    def test_duplicate_offline_order(self):
        """Test that duplicate offline orders are handled correctly"""
        url = reverse('order-list')
        order_data = {
            'offline_id': 'test-offline-123',
            'customer_name': 'Test Customer',
            'payment_method': 'cash',
            'items': [
                {
                    'product': self.product.id,
                    'quantity': 1,
                    'unit_price': '10.99',
                    'total_price': '10.99'
                }
            ],
            'total_amount': '10.99',
            'payment_status': 'completed',
            'status': 'completed'
        }
        
        # First request should succeed
        response = self.client.post(
            url,
            data=json.dumps(order_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Second request with same offline_id should be detected as duplicate
        response = self.client.post(
            url,
            data=json.dumps(order_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'already_processed')
        self.assertEqual(Sale.objects.count(), 1)  # Still only one order in the database


class ServiceWorkerTests(TestCase):
    def test_service_worker_serving(self):
        """Test that the service worker is served correctly"""
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        self.assertIn('ServiceWorker', str(response.content))
    
    def test_offline_page(self):
        """Test that the offline page is served correctly"""
        response = self.client.get('/pos/offline/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/offline.html')
        self.assertContains(response, 'You\'re currently offline')


class CacheControlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser2',
            password='testpass123',
            is_active=True,
            is_staff=True
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_static_files_cached(self):
        """Test that static files have proper cache headers"""
        # Test a sample static file
        response = self.client.get('/static/pos/js/offline-pos.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cache-Control', response)
        self.assertIn('max-age=', response['Cache-Control'])
        self.assertIn('public', response['Cache-Control'])
    
    def test_api_cache_headers(self):
        """Test that API responses have proper cache headers"""
        # This test would need to be adjusted based on your actual API endpoints
        response = self.client.get('/api/pos/products/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cache-Control', response)
        self.assertIn('max-age=', response['Cache-Control'])


class OfflineDataTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser3',
            password='testpass123',
            is_active=True,
            is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create test data
        self.category = Category.objects.create(name='Test Category 2')
        self.products = [
            Product.objects.create(
                name=f'Product {i}',
                price=10.99 + i,
                cost=5.99 + i,
                quantity=50 + i,
                category=self.category,
                branch=self.user.branch
            ) for i in range(3)
        ]
    
    def test_offline_data_endpoint(self):
        """Test that the offline data endpoint returns all required data"""
        # This test assumes you have an endpoint that returns all data needed for offline use
        response = self.client.get('/api/pos/sync/')
        self.assertEqual(response.status_code, 200)
        
        # Check that all products are included
        self.assertEqual(len(response.data.get('products', [])), 3)
        
        # Check that the data is in the expected format
        product = response.data['products'][0]
        self.assertIn('id', product)
        self.assertIn('name', product)
        self.assertIn('price', product)
        self.assertIn('category', product)
    
    def test_offline_data_cache_headers(self):
        """Test that offline data has appropriate cache headers"""
        response = self.client.get('/api/pos/sync/')
        self.assertEqual(response.status_code, 200)
        
        # Check for cache headers
        self.assertIn('Cache-Control', response)
        self.assertIn('max-age=', response['Cache-Control'])
        self.assertIn('public', response['Cache-Control'])
