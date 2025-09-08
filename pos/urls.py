from django.urls import path
from .views import *

app_name = 'pos'

urlpatterns = [
    path('', pos, name='pos' ),
    path('process/sale/', process_sale, name='process_sale'),
    path('sales/list', sales_list, name='sales_list'),
    # path('download-receipt/', generate_receipt_pdf, name='download_receipt'),
    path('product_meal_json/', product_meal_json, name='product_meal_json'),
    path('meal/detail/json/<int:meal_id>/', meal_detail_json, name='meal_detail_json'),
    
    path('change_list/', change_list, name='change_list'),
    path('create_change/', create_change, name='create_change'),
    path('report/', download_change_report, name='download_cashbook_report'),
    path('collect_change/', collect_change, name='collect_change'),

    # sales
    path('sales/<int:user_id>/', void_sales, name='sales'),

    #authenticate
    path('void/authenticate/', void_authenticate, name='void_authenticate'),

    # cash up
    path('cash_up/<int:cashier_id>/', cash_up, name='cash_up'),
    path('update-cashed-amount/<int:cashup_id>/', update_cashed_amount, name='update_cashed_amount'),
    
    #report
    path('cash_up_accountant_report/', accountantreport, name='cash_up_accountant_report'),
    # path('cash_up_admin_report/', adminreport, name='cash_up_admin_report'),

    #cashier handover
    path('handover/', cashier_handover_shift, name='cashier_handover'),

    #authorization to sell
    path('authorize/sell/', check_authorization, name='authorizationstatus'),

    #low production plan stock
    path('low-stock/', lowStockNotification, name='low_stock'),

    # offline
    path('offline/', offline_view, name='offline'),

    # sync
    path('sync/', sync_sales, name='sync_sales'),
    path('get-csrf-token/', get_csrf_token, name='get_csrf_token'),
    path('sync-collections/', sync_collections, name='sync_collections'),
]