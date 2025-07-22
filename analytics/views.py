from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Sum, Count
from datetime import date, timedelta, datetime
from finance.models import Sale, SaleItem, Change, CashierExpense
from loguru import logger
from django.http import JsonResponse
from django.db.models import Sum
from datetime import date, timedelta
from django.db.models.functions import ExtractHour
from collections import defaultdict
import decimal
from permisions.permisions import admin_required
import csv
import pandas as pd
from matplotlib import pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression

@admin_required
def analytics_view(request):
    # Get filter parameters
    filter_by = request.GET.get('filter_by', 'day')
    today = date.today()
    yesterday = today - timedelta(days=1)
    start_of_month = today.replace(day=1)

    data = {}

    if filter_by == 'hour':

        sales_by_hour = SaleItem.objects.filter(sale__date=today, void=False, sale__branch = request.user.branch) \
            .annotate(hour=ExtractHour('time')) \
            .values('hour') \
            .annotate(total_sales=Sum('price')) \
            .order_by('-total_sales')
        data['sales_by_hour'] = list(sales_by_hour)

        logger.info(data)

    elif filter_by == 'day':
        today_sales = Sale.objects.filter(date=today, void=False, branch = request.user.branch, staff = False).aggregate(total=Sum('total_amount'))
        yesterday_sales = Sale.objects.filter(date=yesterday, void=False, branch = request.user.branch, staff = False).aggregate(total=Sum('total_amount'))
        
        today_void_sales = Sale.objects.filter(date=today, void=True, branch = request.user.branch, staff = False).aggregate(total=Sum('total_amount'))
       
        yesterday_void_sales = Sale.objects.filter(date=yesterday, void=True, branch = request.user.branch, staff = False).aggregate(total=Sum('total_amount'))
        
        change_amount = Change.objects.filter(timestamp__date=today, collected=False, sale__branch = request.user.branch).aggregate(total=Sum('amount'))
        yesterday_change_amount = Change.objects.filter(timestamp__date=yesterday, collected=False, sale__branch = request.user.branch).aggregate(total=Sum('amount'))

        data['total_void_sales'] = today_void_sales['total'] or 0
        data['change_amount'] = change_amount['total'] or 0
        data['yesterday_change_amount'] = yesterday_change_amount['total'] or 0

        data['today_sales'] = today_sales['total'] or 0
        data['yesterday_sales'] = yesterday_sales['total'] or 0
        data['yesterday_void_sales'] = yesterday_void_sales['total'] or 0
        
    elif filter_by == 'month':

        month_sales = Sale.objects.filter(date__gte=start_of_month, void=False, branch = request.user.branch).aggregate(total=Sum('total_amount'))
        data['month_sales'] = month_sales['total'] or 0

    elif filter_by == 'year':
        
        year_sales = Sale.objects.filter(date__gte=start_of_year, void=False, branch = request.user.branch).aggregate(total=Sum('total_amount'))
        data['year_sales'] = year_sales['total'] or 0

    # Best-selling dish
    best_selling_meal = SaleItem.objects.filter(meal__isnull=False, sale__date=today, sale__branch = request.user.branch, sale__staff=False).values('meal__name') \
    .annotate(total_sold=Sum('quantity')) \
    .order_by('-total_sold') \
    .first()

    best_selling_dish = SaleItem.objects.filter(dish__isnull=False, sale__date=today, sale__branch = request.user.branch, sale__staff=False).values('dish__name') \
    .annotate(total_sold=Sum('quantity')) \
    .order_by('-total_sold') \
    .first()

    # logger.info(best_selling_dish['dish__name'])
    # logger.info(best_selling_meal['meal__name'])
   
    data['best_selling_meal'] = best_selling_meal or ''
    data['best_selling_dish'] = best_selling_dish or ''
    
    
    grouped_meals = defaultdict(lambda: {})
    grouped_dishes = defaultdict(lambda: {})
    staff_dishes = defaultdict(lambda: {})

    sales = SaleItem.objects.filter(sale__date = today, sale__void=False, sale__staff=False, sale__branch = request.user.branch).select_related('sale', 'meal', 'dish', 'product').all()

    staff_sales = SaleItem.objects.filter(sale__date = today, sale__void=False, sale__staff=True, sale__branch = request.user.branch).select_related('sale', 'meal', 'dish', 'product').all()

    sales_dishes = SaleItem.objects.filter(sale__date = today, sale__void=False, sale__staff=False, sale__branch = request.user.branch)

    dishes = defaultdict(lambda: {})


    for sale in sales_dishes:
        if sale.meal:
            sale_date = sale.sale.date
            category = (
                'Today' if sale_date == today
                else 'Yesterday' if sale_date == yesterday
                else sale_date.strftime('%A, %d %B %Y')
            )
            for dish in sale.meal.dish.all():
                if dish.name in dishes[category]:
                    dishes[category][dish.name]['quantity'] += sale.quantity
                    dishes[category][dish.name]['price'] += sale.price * sale.quantity
                else:
                    dishes[category][dish.name] = {
                        'name': dish.name,
                        'quantity': sale.quantity,
                        'price': sale.price * sale.quantity,
                    }

    for sale in staff_sales:
        sale_date = sale.sale.date
        category = (
            'Today' if sale_date == today
            else 'Yesterday' if sale_date == yesterday
            else sale_date.strftime('%A, %d %B %Y')
        )
        
        if sale.meal:
            for dish in sale.meal.dish.all():
                if dish.name in staff_dishes[category]:
                    staff_dishes[category][dish.name]['quantity'] += sale.quantity
                    staff_dishes[category][dish.name]['price'] += sale.price * sale.quantity
                else:
                    staff_dishes[category][dish.name] = {
                        'name': dish.name,
                        'quantity': sale.quantity,
                        'price': sale.price * sale.quantity,
                    }
        elif sale.dish:
                dish_name = sale.dish.name
                if dish_name in staff_dishes[category]:

                    staff_dishes[category][dish_name]['quantity'] += sale.quantity
                    staff_dishes[category][dish_name]['price'] += sale.price * sale.quantity
                else:
                    staff_dishes[category][dish_name] = {
                        'name': dish_name,
                        'quantity': sale.quantity,
                        'price': sale.price * sale.quantity,
                    }
                    

    formatted_staff_dishes = {category: list(items.values()) for category, items in staff_dishes.items()}
    data['staff_dishes'] = dict(formatted_staff_dishes)

    logger.info(staff_dishes) 

    if not sales:
        logger.warning("No sales data found.")
    else:
        for sale in sales:
            sale_date = sale.sale.date
            category = (
                'Today' if sale_date == today
                else 'Yesterday' if sale_date == yesterday
                else sale_date.strftime('%A, %d %B %Y')
            )

            if sale.meal:
                meal_name = sale.meal.name
                logger.info(f'{meal_name} : {sale.meal.price}')
                if meal_name in grouped_meals[category]:
                    grouped_meals[category][meal_name]['quantity'] += sale.quantity
                    grouped_meals[category][meal_name]['price'] += decimal.Decimal(sale.meal.price) * sale.quantity
                else:

                    grouped_meals[category][meal_name] = {
                        'name': meal_name,
                        'quantity': sale.quantity,
                        'price': sale.price * sale.quantity,
                    }

            elif sale.dish:
                dish_name = sale.dish.name
                if dish_name in grouped_dishes[category]:
                    logger.info(f'{dish_name} : {sale.dish.price}')

                    grouped_dishes[category][dish_name]['quantity'] += sale.quantity
                    grouped_dishes[category][dish_name]['price'] += (sale.dish.price * sale.quantity)
                else:
                    grouped_dishes[category][dish_name] = {
                        'name': dish_name,
                        'quantity': sale.quantity,
                        'price': sale.price * sale.quantity,
                    }
                    logger.info(f'{dish_name} : {sale.dish.price}')
            elif sale.product:
                product_name = sale.product.name
                if product_name in grouped_dishes[category]:
                    grouped_dishes[category][product_name]['quantity'] += sale.quantity
                    grouped_dishes[category][product_name]['price'] += sale.price * sale.quantity
                else:
                    grouped_dishes[category][product_name] = {
                        'name': product_name,
                        'quantity': sale.quantity,
                        'price': sale.price * sale.quantity,
                    }

    formatted_meals = {category: list(items.values()) for category, items in grouped_meals.items()}
    formatted_dishes = {category: list(items.values()) for category, items in grouped_dishes.items()}
    f_dishes = {category: list(items.values()) for category, items in dishes.items()}

    combined_dishes = defaultdict(lambda: {})

    for category, items in grouped_dishes.items():
        for dish_name, dish_data in items.items():
            if dish_name in combined_dishes[category]:
                combined_dishes[category][dish_name]['quantity'] += dish_data['quantity']
                combined_dishes[category][dish_name]['price'] += dish_data['price']
            else:
                combined_dishes[category][dish_name] = dish_data.copy()

    for category, items in dishes.items():
        for dish_name, dish_data in items.items():
            if dish_name in combined_dishes[category]:
                combined_dishes[category][dish_name]['quantity'] += dish_data['quantity']
                combined_dishes[category][dish_name]['price'] += dish_data['price']
            else:
                combined_dishes[category][dish_name] = dish_data.copy()

    # Convert combined_dishes to the desired format
    f_dishes = {category: list(items.values()) for category, items in combined_dishes.items()}

    data['dishes'] = dict(f_dishes)
    data['grouped_meals'] = dict(formatted_meals)
    data['grouped_dishes'] = dict(formatted_dishes)
    logger.info(data)
    return JsonResponse(data)

@admin_required
def analytics_index(request):
    return render(request, 'analytics.html')


def analysis(request):
    sales_list = []

    sales_by_day = Sale.objects.filter(void = False)

    for sales in sales_by_day:
        logger.info(sales.date)
        
        combined_sales = sales.date.strftime('%m-%Y')

        found = False
        if sales_list:
            for items in sales_list:
                items_date = datetime.strptime(items['Date'], '%m-%Y')
                
                combined = items_date.strftime('%m-%Y')
                                              
                if combined == combined_sales:
                    items['Total_Amount'] += sales.total_amount
                    found = True
                    break
        
        if not found:
            sales_list.append(
                {
                    'Date': sales.date.strftime('%m-%Y'),
                    'Total_Amount': sales.total_amount
                }
            )
    
    if sales_list:
        with open('analytics.csv', 'w', newline='') as file:
            fieldnames = sales_list[0].keys()

            writer = csv.DictWriter(file, fieldnames=fieldnames)
        
            writer.writeheader()
            writer.writerows(sales_list)
    
    try:
        df = pd.read_csv('analytics.csv')
        print(df.head())

        X = df.iloc[0:,0].values
        print(X[0:5])

        y = df.iloc[0:,1].values
        print(y[0:5])

        plt.scatter(X,y)
        plt.title('Income: Sales')
        plt.savefig('Sales_plot.png')

        df['Date'] = pd.to_datetime(df['Date'], format='%m-%Y')
        df['Month_Index'] = (df['Date'] - df['Date'].min()).dt.days // 30

        X= df[['Month_Index']]
        y = df['Total_Amount']

        model = LinearRegression()
        model.fit(X,y)

        future_dates = pd.to_datetime(['08-2025', '09-2025', '10-2025'], format='%m-%Y')

        future_months = (future_dates - df['Date'].min()).days // 30

        future_predictions = model.predict(np.array(future_months).reshape(-1, 1))

        for date, pred in zip(future_dates.strftime('%m-%Y'), future_predictions):
            print(f"Predicted earnings for {date}: ${pred:.2f}")

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False})


def analysisExpenses(request):
    expenses_list = []

    expenses_by_month = CashierExpense.objects.all()

    for expenses in expenses_by_month:
        logger.info(expenses.date)
        
        combined_sales = expenses.date.strftime('%d-%m-%Y')

        found = False
        if expenses_list:
            for items in expenses_list:
                items_date = datetime.strptime(items['Date'], '%d-%m-%Y')
                
                combined = items_date.strftime('%d-%m-%Y')
                                              
                if combined == combined_sales:
                    items['Total_Amount'] += expenses.amount
                    found = True
                    break
        
        if not found:
            expenses_list.append(
                {
                    'Date': expenses.date.strftime('%d-%m-%Y'),
                    'Total_Amount': expenses.amount
                }
            )
    
    if expenses_list:
        with open('analytics_expenses.csv', 'w', newline='') as file:
            fieldnames = expenses_list[0].keys()

            writer = csv.DictWriter(file, fieldnames=fieldnames)
        
            writer.writeheader()
            writer.writerows(expenses_list)
    
    try:
        df = pd.read_csv('analytics_expenses.csv')
        print(df.head())

        X = df.iloc[0:,0].values
        print(X[0:5])

        y = df.iloc[0:,1].values
        print(y[0:5])

        plt.scatter(X,y)
        plt.title('Expenses')
        plt.savefig('Expense_plot.png')

        df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y')
        df['Month_Index'] = (df['Date'] - df['Date'].min()).dt.days // 30

        X= df[['Month_Index']]
        y = df['Total_Amount']

        model = LinearRegression()
        model.fit(X,y)

        future_dates = pd.to_datetime(['01-08-2025', '01-09-2025', '01-10-2025'], format='%d-%m-%Y')

        future_months = (future_dates - df['Date'].min()).days // 30

        future_predictions = model.predict(np.array(future_months).reshape(-1, 1))

        for date, pred in zip(future_dates.strftime('%d-%m-%Y'), future_predictions):
            print(f"Predicted earnings for {date}: ${pred:.2f}")

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False})
