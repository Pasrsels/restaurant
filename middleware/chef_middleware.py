from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.conf import settings

class ChefAccessMiddleware:
    """
    Middleware to restrict chef access to only production-related pages.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Define allowed URLs for chefs
        self.chef_allowed_urls = [
            # Production Plans
            '/inventory/production/plan/list',
            '/inventory/production/plan/admin',
            '/inventory/create/production/plan',
            '/inventory/production_plan/detail/',
            '/inventory/confirm/production_plan/',
            '/inventory/declare/production_plan/',
            '/inventory/process/production_plan/',
            '/inventory/update_production_plan/',
            '/inventory/production-plan/delete/',
            '/inventory/declare-production-plan/',
            '/inventory/latest-declare-production-plan/',
            
            # Transfers
            '/inventory/transfers',
            '/inventory/production_transfers/',
            '/inventory/accept_transfer/',
            '/inventory/receive_transfer_detail/',
            '/inventory/add/transfer/',
            
            # Dishes and Meals
            '/inventory/dishes/',
            '/inventory/meal/',
            '/inventory/dish/',
            '/inventory/ingredients/',
            '/inventory/add/meal/',
            '/inventory/meals/',
            '/inventory/create/meal/category/',
            '/inventory/filter/meal/category/',
            
            # Production Raw Materials
            '/inventory/production_raw_materials/',
            '/inventory/production_rm/detail/',
            '/inventory/minor_raw_materials/',
            '/inventory/confirm/minor_raw_materials/',
            '/inventory/process/minor_raw_materials/',
            '/inventory/override/raw-material',
            
            # End of Day
            '/inventory/end-of-day/',
            '/inventory/end-of-day-json/',
            '/inventory/save-end-of-day/',
            '/inventory/confirm_end_of_day/',
            '/inventory/end_of_day_detail/',
            '/inventory/end_of_day_list/',
            '/inventory/end_of_day_pdf_report',
            
            # Check Lists
            '/inventory/check_list/',
            '/inventory/check_list/all',
            '/inventory/check_list/finished',
            '/inventory/check_list/raw',
            
            # Authentication
            '/users/logout/',
            '/users/login/',
            
            # Static and Media files
            '/static/',
            '/media/',
            
            # AJAX and API endpoints
            '/inventory/dish_json_detail/',
            '/inventory/dish_data_json/',
            '/inventory/raw_material_json/',
            '/inventory/confirm_declaration/',
            '/inventory/yesterdays/left/overs/',
            '/inventory/declared/production/plan/',
            '/inventory/production/declaration/table/ajax',
        ]
    
    def __call__(self, request):
        # Check if user is authenticated and is a chef
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.role == 'chef':
            # Allow chefs full access - no restrictions
            pass
 
        return self.get_response(request)
