from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    ProductViewSet, CategoryViewSet, MenuViewSet,
    OrderViewSet, SyncViewSet
)

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'menu', MenuViewSet, basename='menu')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'sync', SyncViewSet, basename='sync')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
]
