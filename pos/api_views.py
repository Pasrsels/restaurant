from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.db.models import Prefetch
from inventory.models import Product, Category, Dish, Meal
from finance.models import Sale, SaleItem
from .serializers import ProductSerializer, CategorySerializer, OrderSerializer, DishSerializer, MealSerializer

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for retrieving products with caching."""
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Check if we have a cached version
        cache_key = f'products_branch_{self.request.user.branch.id}'
        products = cache.get(cache_key)
        
        if products is None:
            # Cache miss, query the database
            products = Product.objects.filter(
                branch=self.request.user.branch,
                deactivate=False
            ).select_related('category', 'unit')
            
            # Cache for 1 hour
            cache.set(cache_key, products, 3600)
            
        return products
    
    @method_decorator(cache_page(60 * 60))  # Cache for 1 hour
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for retrieving categories with caching."""
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        cache_key = f'categories_branch_{self.request.user.branch.id}'
        categories = cache.get(cache_key)
        
        if categories is None:
            categories = Category.objects.filter(
                product__branch=self.request.user.branch,
                product__deactivate=False
            ).distinct()
            cache.set(cache_key, categories, 3600)
            
        return categories

class MenuViewSet(viewsets.ViewSet):
    """API endpoint for retrieving menu items (dishes and meals) with caching."""
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        branch = request.user.branch
        cache_key = f'menu_branch_{branch.id}'
        
        menu_data = cache.get(cache_key)
        
        if menu_data is None:
            # Get active dishes and meals
            dishes = Dish.objects.filter(
                branch=branch,
                deactivate=False
            )
            
            meals = Meal.objects.filter(
                branch=branch,
                deactivate=False
            ).prefetch_related('dishes')
            
            # Serialize the data
            dish_serializer = DishSerializer(dishes, many=True)
            meal_serializer = MealSerializer(meals, many=True)
            
            menu_data = {
                'dishes': dish_serializer.data,
                'meals': meal_serializer.data
            }
            
            # Cache for 1 hour
            cache.set(cache_key, menu_data, 3600)
        
        return Response(menu_data)

class OrderViewSet(viewsets.ViewSet):
    """API endpoint for processing orders with offline support."""
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def create(self, request):
        serializer = OrderSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                # Check if this is a retry of a previously failed order
                if 'offline_id' in request.data:
                    # Check if this order was already processed
                    if self._is_order_processed(request.data['offline_id']):
                        return Response(
                            {'status': 'already_processed'},
                            status=status.HTTP_200_OK
                        )
                
                # Process the order
                order = serializer.save()
                
                # If this was an offline order, mark it as synced
                if 'offline_id' in request.data:
                    self._mark_order_as_synced(request.data['offline_id'])
                
                return Response(
                    {'status': 'success', 'order_id': order.id},
                    status=status.HTTP_201_CREATED
                )
                
            except Exception as e:
                # Log the error for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error processing order: {str(e)}")
                
                # If this was an offline order, return a 202 to indicate it should be retried
                if 'offline_id' in request.data:
                    return Response(
                        {'status': 'retry_later'},
                        status=status.HTTP_202_ACCEPTED
                    )
                
                # For online orders, return an error
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def _is_order_processed(self, offline_id):
        """Check if an offline order was already processed."""
        # This is a simplified example. In a real app, you'd want to store
        # a mapping of offline_id to order_id in your database
        return False
    
    def _mark_order_as_synced(self, offline_id):
        """Mark an offline order as successfully synced."""
        # In a real app, you'd update your database here
        pass

class SyncViewSet(viewsets.ViewSet):
    """API endpoint for syncing offline data."""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def sync_orders(self, request):
        """Sync multiple orders from offline storage."""
        orders = request.data.get('orders', [])
        results = []
        
        for order_data in orders:
            # Use the OrderViewSet to process each order
            view = OrderViewSet.as_view({'post': 'create'})
            response = view(request._request)
            
            results.append({
                'offline_id': order_data.get('offline_id'),
                'status': response.status_code,
                'data': response.data
            })
        
        return Response({'results': results})
    
    @action(detail=False, methods=['get'])
    def last_sync(self, request):
        """Get the last sync timestamp."""
        # In a real app, you'd store and retrieve this from your database
        return Response({
            'last_sync': timezone.now().isoformat()
        })
