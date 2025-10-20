
from django.db import models
from .models import Sale, Expense


def calculate_cashier_sales(cashier, date, branch):
    """
        generate void sales, normal sales
    """
    sales = Sale.objects.filter(date=date).select_related('branch')

    normal_sales = sales.filter(
        void=False,
        staff=False
    ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    void_sales = sales.filter(
        void=True,
        staff=False
    ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    return {
        'normal_sales': normal_sales,
        'void_sales': void_sales,
    }
    
def calculate_cashier_expenses(cashier, date, branch):
    """cashier expense"""
    expenses_total = Expense.objects.filter(date=date, user=cashier, branch=branch).select_for_update('branch').aggregate(
        total=models.Sum('amount')
    )['total'] or 0
    
    return {
        'expenses_total':expenses_total
    }
    

def calculate_cashier_expenses(cashier, date, branch):
    """cashier expense"""
    expenses_total = Expense.objects.filter(date=date, user=cashier, branch=branch).select_for_update('branch').aggregate(
        total=models.Sum('amount')
    )['total'] or 0
    
    return {
        'expenses_total':expenses_total
    }

def save_cashier_expenses(cashier, amount, description, branch, name):
    """cashier expense"""
    
    Expense.objects.create(
        name = name,
        amount = amount,
        description = description,
        user = cashier,
        branch = branch,
        status = False,
        track_amount = amount
    )