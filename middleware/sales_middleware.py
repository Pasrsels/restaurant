# sales_middleware.py

from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.conf import settings

class SalesAccessMiddleware:
    """
    Middleware to restrict access to specific views for sales personnel only.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.sales_only_urls = getattr(settings, 'SALES_ONLY_URLS', ['/pos/'])
    
    def __call__(self, request):
        current_path = request.path_info
        print(current_path)
        is_sales_only_url = any(current_path.startswith(url) for url in self.sales_only_urls)
        
        if is_sales_only_url:
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this area.")
                return redirect(f"{reverse('login')}?next={request.path}")

            if not self.is_sales_personnel(request.user):
                messages.error(request, "This area is restricted to sales personnel only.")
                return redirect('users:login')
 
        return self.get_response(request)
    
    def is_sales_personnel(self, user):
        """
        Check if the user is sales personnel.
        
        You can customize this method based on how you identify sales personnel in your system:
        - Using a specific group, e.g., "Sales"
        - Using a custom user field, e.g., user.department == "Sales"
        - Using permissions
        """
        if hasattr(user, 'role') and user.role == 'sales':
            return True
        
        return False