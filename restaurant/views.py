from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
from finance.models import Sale, SaleItem, Expense
from users.models import Branch
import json
from loguru import logger

@login_required
def dashboard_view(request): 
    selected_branch = request.GET.get('branch', 'all')

    logger.info(f'selected brancg: {selected_branch}')
    logger.info(f'is superuser: {getattr(request.user, "is_superuser", False)}')
    logger.info(f'is staff: {getattr(request.user, "is_staff", False)}')
    logger.info(f'branch id: {getattr(request.user, "branch_id", None)}')
    
    if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
        branches = Branch.objects.all()
    else:
        branches = Branch.objects.filter(id=getattr(request.user, 'branch_id', None))
        selected_branch = getattr(request.user, 'branch_id', None)
    
    today = timezone.now().date()
    
    sales_qs = Sale.objects.filter(date=today, void=False)
    expenses_qs = Expense.objects.filter(date=today, cancel=False)
    if selected_branch and selected_branch != 'all':
        sales_qs = sales_qs.filter(branch_id=selected_branch)
        expenses_qs = expenses_qs.filter(branch_id=selected_branch)

    total_orders = sales_qs.count()
    total_clients = total_orders
    total_revenue = sales_qs.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_expenses = expenses_qs.aggregate(Sum('amount'))['amount__sum'] or 0
    revenue_ratio = total_revenue - total_expenses

    total_menus = SaleItem.objects.filter(sale__in=sales_qs).values('meal', 'dish', 'product').distinct().count()
    
    context = {
        'branches': branches,
        'selected_branch': selected_branch,
        'total_menus': total_menus,
        'total_orders': total_orders,
        'total_clients': total_clients,
        'revenue_day_ratio': revenue_ratio,
    }
    
    return render(request, 'dashboard.html', context)


@login_required
def dashboard_stats_api(request):
    """API endpoint for dashboard statistics"""
    period = request.GET.get('period', 'today')
    branch_id = request.GET.get('branch', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date and end_date:
        date_from = datetime.strptime(start_date, '%Y-%m-%d').date()
        date_to = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        date_from, date_to = get_date_range(period)
    
    sales_query = Sale.objects.filter(date__gte=date_from, date__lte=date_to, void=False)
    expenses_query = Expense.objects.filter(date__gte=date_from, date__lte=date_to, cancel=False)

    if not (getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False)):
        branch_id = getattr(request.user, 'branch_id', None)

    if branch_id and branch_id != 'all':
        sales_query = sales_query.filter(branch_id=branch_id)
        expenses_query = expenses_query.filter(branch_id=branch_id)

    total_orders = sales_query.count()
    total_clients = total_orders  
    total_revenue = sales_query.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_expenses = expenses_query.aggregate(Sum('amount'))['amount__sum'] or 0
    revenue_ratio = total_revenue - total_expenses
    

    total_menus = SaleItem.objects.filter(
        sale__in=sales_query
    ).values('meal', 'dish', 'product').distinct().count()
    
    target_orders = 300
    target_clients = 300
    target_revenue = 50000 # to be dynamic
    
    orders_percentage = min(int((total_orders / target_orders) * 100), 100) if target_orders > 0 else 0
    clients_percentage = min(int((total_clients / target_clients) * 100), 100) if target_clients > 0 else 0
    revenue_percentage = min(int((total_revenue / target_revenue) * 100), 100) if target_revenue > 0 else 0
    
    revenue_chart_data = get_revenue_chart_data(date_from, date_to, branch_id, period)
    orders_chart_data = get_orders_chart_data(date_from, date_to, branch_id, period)
    

    orders_list = get_orders_list(sales_query.order_by('-date', '-id')[:50])
    
    data = {
        'stats': {
            'total_menus': total_menus,
            'total_orders': total_orders,
            'total_clients': total_clients,
            'revenue_ratio': float(revenue_ratio),
            'orders_percentage': orders_percentage,
            'clients_percentage': clients_percentage,
            'revenue_percentage': revenue_percentage,
        },
        'charts': {
            'revenue': revenue_chart_data,
            'orders': orders_chart_data,
        },
        'orders': orders_list,
    }
    
    return JsonResponse(data)


@login_required
def chart_data_api(request):
    """API endpoint for individual chart data"""
    chart_type = request.GET.get('chart_type')
    period = request.GET.get('period', 'weekly')
    branch_id = request.GET.get('branch', 'all')

    date_from, date_to = get_date_range(period)
    
    # Restrict non-admins to their branch
    if not (getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False)):
        branch_id = getattr(request.user, 'branch_id', None)

    if chart_type == 'revenue':
        data = get_revenue_chart_data(date_from, date_to, branch_id, period)
    elif chart_type == 'orders':
        data = get_orders_chart_data(date_from, date_to, branch_id, period)
    else:
        data = {}
    
    return JsonResponse(data)


@login_required
def orders_list_api(request):
    """API endpoint for orders list"""
    period = request.GET.get('period', 'monthly')
    branch_id = request.GET.get('branch', 'all')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 10))
    
    date_from, date_to = get_date_range(period)
    
    sales_query = Sale.objects.filter(date__gte=date_from, date__lte=date_to, void=False)

    # Restrict non-admins to their branch
    if not (getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False)):
        branch_id = getattr(request.user, 'branch_id', None)
    
    if branch_id and branch_id != 'all':
        sales_query = sales_query.filter(branch_id=branch_id)
    
    sales_query = sales_query.order_by('-date', '-id')
    
    orders_list = get_orders_list(sales_query)
    
    return JsonResponse({'orders': orders_list})


def get_date_range(period):
    """Get date range based on period"""
    today = timezone.now().date()
    
    if period == 'today':
        return today, today
    elif period == 'weekly':
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    elif period == 'monthly':
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end
    elif period == 'yearly':
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        return start, end
    else:
        return today, today


def get_revenue_chart_data(date_from, date_to, branch_id, period):
    """Get revenue chart data"""
    sales_query = Sale.objects.filter(date__gte=date_from, date__lte=date_to, void=False)
    expenses_query = Expense.objects.filter(date__gte=date_from, date__lte=date_to, cancel=False)
    
    if branch_id != 'all':
        sales_query = sales_query.filter(branch_id=branch_id)
        expenses_query = expenses_query.filter(branch_id=branch_id)
    
    if period == 'today':
        labels = [f"{i:02d}:00" for i in range(24)]
        income_data = [0] * 24
        expenses_data = [0] * 24
        
        for sale in sales_query:
            hour = sale.saleitem_set.first().time.hour if sale.saleitem_set.exists() else 0
            income_data[hour] += float(sale.total_amount)
        
        for expense in expenses_query:
            expenses_data[12] += float(expense.amount)
            
    elif period == 'weekly':
        labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        income_data = [0] * 7
        expenses_data = [0] * 7
        
        for sale in sales_query:
            day_index = sale.date.weekday()
            income_data[day_index] += float(sale.total_amount)
        
        for expense in expenses_query:
            day_index = expense.date.weekday()
            expenses_data[day_index] += float(expense.amount)
            
    elif period == 'monthly':
        delta = date_to - date_from
        weeks = (delta.days // 7) + 1
        labels = [f"Week {i+1}" for i in range(weeks)]
        income_data = [0] * weeks
        expenses_data = [0] * weeks
        
        for sale in sales_query:
            week_index = (sale.date - date_from).days // 7
            if week_index < weeks:
                income_data[week_index] += float(sale.total_amount)
        
        for expense in expenses_query:
            week_index = (expense.date - date_from).days // 7
            if week_index < weeks:
                expenses_data[week_index] += float(expense.amount)
                
    else:  
        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        income_data = [0] * 12
        expenses_data = [0] * 12
        
        for sale in sales_query:
            month_index = sale.date.month - 1
            income_data[month_index] += float(sale.total_amount)
        
        for expense in expenses_query:
            month_index = expense.date.month - 1
            expenses_data[month_index] += float(expense.amount)
    
    return {
        'labels': labels,
        'income': income_data,
        'expenses': expenses_data,
    }


def get_orders_chart_data(date_from, date_to, branch_id, period):
    """Get orders chart data"""
    sales_query = Sale.objects.filter(date__gte=date_from, date__lte=date_to, void=False)
    
    if branch_id != 'all':
        sales_query = sales_query.filter(branch_id=branch_id)
    
    if period in ['today', 'weekly']:
        if period == 'today':
            dates = [date_from]
        else:
            dates = [date_from + timedelta(days=i) for i in range(7)]
        
        labels = [d.strftime('%b %d') for d in dates]
        data = []
        
        for date in dates:
            count = sales_query.filter(date=date).count()
            data.append(count)
    else:
        labels = ['Point 1', 'Point 2', 'Point 3', 'Point 4']
        delta = (date_to - date_from).days
        interval = delta // 4
        
        data = []
        for i in range(4):
            start = date_from + timedelta(days=i * interval)
            end = start + timedelta(days=interval)
            count = sales_query.filter(date__gte=start, date__lt=end).count()
            data.append(count)
    
    return {
        'labels': labels,
        'data': data,
    }


def get_orders_list(sales_query):
    """Get formatted orders list"""
    orders = []
    
    for sale in sales_query:
        status = 'completed' if sale.cash_type == 'solid-cash' else 'delivery'
        status_display = 'New Order' if not sale.staff else 'On Delivery'
        
        orders.append({
            'id': sale.id,
            'receipt_number': sale.receipt_number,
            'date': sale.date.isoformat(),
            'cashier_name': sale.cashier.get_full_name() or sale.cashier.username,
            'branch_name': sale.branch.name if sale.branch else 'N/A',
            'total_amount': str(sale.total_amount),
            'status': status,
            'status_display': status_display,
        })
    
    return orders