from django.urls import path
from .views import *

urlpatterns = [
    path('analytics/', analytics_view, name='analytics_overview'),
    path('index/', analytics_index, name='analytics_index'),
    path('analysis/', analysis, name='analysis'),
    path('analysis-expenses/', analysisExpenses, name='analysis_expenses'),
    path('sales_dishes/', dish_analytics, name='dish_analytics')
]
