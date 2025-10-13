from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Ingredient, Dish, ProductionItems
from .permisions.permisions import chef_or_stores_view_required

@login_required
@chef_or_stores_view_required
def stock_analysis_api(request):
    """API endpoint for stock analysis data"""
    try:
        # Get filter parameters
        product_type = request.GET.get('product_type')
        stock_status = request.GET.get('stock_status')
        search = request.GET.get('search')
        
        # Base queryset - combine ingredients and dishes
        data = []
        
        # Get ingredients
        ingredients = Ingredient.objects.all()
        if search:
            ingredients = ingredients.filter(name__icontains=search)
        
        for ingredient in ingredients:
            # Determine stock status
            current_stock = ingredient.current_stock or 0
            min_stock = ingredient.min_stock_level or 0
            
            if current_stock <= 0:
                stock_status_value = 'out_of_stock'
            elif current_stock <= min_stock:
                stock_status_value = 'low_stock'
            else:
                stock_status_value = 'in_stock'
            
            # Apply filters
            if stock_status and stock_status != 'all' and stock_status_value != stock_status:
                continue
                
            if product_type and product_type != 'all':
                if product_type == 'ingredient' and ingredient.type != 'ingredient':
                    continue
                elif product_type == 'raw' and ingredient.type != 'raw':
                    continue
            
            data.append({
                'id': f"ingredient_{ingredient.id}",
                'name': ingredient.name,
                'type': ingredient.type or 'ingredient',
                'description': ingredient.description or '',
                'current_stock': current_stock,
                'min_stock_level': min_stock,
                'stock_status': stock_status_value,
                'unit': ingredient.unit,
                'last_updated': ingredient.updated_at.isoformat() if ingredient.updated_at else ingredient.created_at.isoformat()
            })
        
        # Get dishes (finished products)
        dishes = Dish.objects.all()
        if search:
            dishes = dishes.filter(name__icontains=search)
        
        for dish in dishes:
            # For dishes, we might not have stock tracking, so we'll show as available
            current_stock = getattr(dish, 'current_stock', 0) or 0
            min_stock = getattr(dish, 'min_stock_level', 0) or 0
            
            if current_stock <= 0:
                stock_status_value = 'out_of_stock'
            elif current_stock <= min_stock:
                stock_status_value = 'low_stock'
            else:
                stock_status_value = 'in_stock'
            
            # Apply filters
            if stock_status and stock_status != 'all' and stock_status_value != stock_status:
                continue
                
            if product_type and product_type != 'all':
                if product_type == 'finished' and dish.type != 'finished':
                    continue
            
            data.append({
                'id': f"dish_{dish.id}",
                'name': dish.name,
                'type': 'finished',
                'description': dish.description or '',
                'current_stock': current_stock,
                'min_stock_level': min_stock,
                'stock_status': stock_status_value,
                'unit': 'portions',
                'last_updated': dish.updated_at.isoformat() if hasattr(dish, 'updated_at') and dish.updated_at else dish.created_at.isoformat()
            })
        
        # Sort by name
        data.sort(key=lambda x: x['name'])
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def stock_item_details_api(request, item_id):
    """API endpoint for detailed stock item information"""
    try:
        item_type, item_pk = item_id.split('_', 1)
        
        if item_type == 'ingredient':
            item = Ingredient.objects.get(id=item_pk)
            usage_history = []  # You can implement usage history tracking here
            
            data = {
                'id': item.id,
                'name': item.name,
                'type': item.type or 'ingredient',
                'description': item.description or '',
                'current_stock': item.current_stock or 0,
                'min_stock_level': item.min_stock_level or 0,
                'unit': item.unit,
                'stock_status': get_stock_status(item.current_stock or 0, item.min_stock_level or 0),
                'last_updated': item.updated_at.isoformat() if item.updated_at else item.created_at.isoformat(),
                'usage_history': usage_history
            }
        elif item_type == 'dish':
            item = Dish.objects.get(id=item_pk)
            usage_history = []  # You can implement usage history tracking here
            
            data = {
                'id': item.id,
                'name': item.name,
                'type': 'finished',
                'description': item.description or '',
                'current_stock': getattr(item, 'current_stock', 0) or 0,
                'min_stock_level': getattr(item, 'min_stock_level', 0) or 0,
                'unit': 'portions',
                'stock_status': get_stock_status(getattr(item, 'current_stock', 0) or 0, getattr(item, 'min_stock_level', 0) or 0),
                'last_updated': item.updated_at.isoformat() if hasattr(item, 'updated_at') and item.updated_at else item.created_at.isoformat(),
                'usage_history': usage_history
            }
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid item type'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except (Ingredient.DoesNotExist, Dish.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': 'Item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def production_item_details_api(request, item_id):
    """API endpoint for detailed production item information"""
    try:
        # Parse the item_id to extract plan_id, item_id, and type
        parts = item_id.split('-')
        if len(parts) >= 3:
            plan_id = parts[0]
            item_id_part = parts[1]
            item_type = parts[2]
            
            if item_type == 'portion':
                # Handle dish/portion items
                production_item = ProductionItems.objects.get(id=item_id_part)
                dish = production_item.dish
                
                data = {
                    'id': production_item.id,
                    'item_name': dish.name,
                    'type': 'Dish',
                    'plan_number': production_item.production.production_plan_number,
                    'date': production_item.production.date_created.isoformat(),
                    'planned_quantity': production_item.planned_portions or 0,
                    'produced_quantity': production_item.portions or 0,
                    'variance': (production_item.portions or 0) - (production_item.planned_portions or 0),
                    'unit': 'portions',
                    'status': get_production_status(production_item.production),
                    'notes': production_item.notes or '',
                    'responsible_person': production_item.production.created_by.username if production_item.production.created_by else 'Not specified'
                }
            else:
                # Handle ingredient items
                data = {
                    'id': item_id,
                    'item_name': 'Ingredient Item',
                    'type': 'Ingredient',
                    'plan_number': 'N/A',
                    'date': 'N/A',
                    'planned_quantity': 0,
                    'produced_quantity': 0,
                    'variance': 0,
                    'unit': 'N/A',
                    'status': 'N/A',
                    'notes': 'Ingredient details not available',
                    'responsible_person': 'Not specified'
                }
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid item ID format'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except ProductionItems.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Production item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def notifications_api(request):
    """API endpoint for notifications"""
    try:
        # For now, we'll return mock notifications
        # In a real implementation, you'd have a Notification model
        notifications = [
            {
                'id': 1,
                'title': 'Low Stock Alert',
                'message': 'Tomatoes are running low on stock',
                'timestamp': '2024-01-15T10:30:00Z',
                'type': 'stock_alert'
            },
            {
                'id': 2,
                'title': 'Production Plan Confirmed',
                'message': 'Production plan #123 has been confirmed by chef',
                'timestamp': '2024-01-15T09:15:00Z',
                'type': 'production_update'
            }
        ]
        
        return JsonResponse({
            'success': True,
            'notifications': notifications
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@chef_or_stores_view_required
def clear_notifications_api(request):
    """API endpoint to clear notifications"""
    if request.method == 'POST':
        try:
            # In a real implementation, you'd mark notifications as read
            # For now, we'll just return success
            return JsonResponse({
                'success': True,
                'message': 'Notifications cleared successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    else:
        return JsonResponse({
            'success': False,
            'error': 'Method not allowed'
        }, status=405)

def get_stock_status(current_stock, min_stock):
    """Helper function to determine stock status"""
    if current_stock <= 0:
        return 'out_of_stock'
    elif current_stock <= min_stock:
        return 'low_stock'
    else:
        return 'in_stock'

def get_production_status(production):
    """Helper function to determine production status"""
    if production.status and production.declared:
        return 'completed'
    elif production.declared:
        return 'declared'
    elif production.status:
        return 'confirmed'
    else:
        return 'pending'
