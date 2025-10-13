import csv
from . models import *
import datetime, json
from loguru import logger
from . forms import (
    CashUpForm,
    ExpensesForm,
    ExpenseCategoryForm
)
from xhtml2pdf import pisa
from decimal import Decimal
from datetime import  timedelta
from django.db.models import Sum
from django.db import transaction
from .models import Sale, Expense, CashierPayments
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from . tasks import send_expense_creation_notification
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from inventory.models import Logs
from permisions.permisions import admin_required
from collections import defaultdict
from .utilities import *
from django.db.models import Q

def get_previous_month():
    first_day_of_current_month = datetime.datetime.now().replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
    return last_day_of_previous_month.month

def get_current_month():
    return datetime.datetime.now().month

def get_current_year():
    return datetime.datetime.now().year


@login_required
def sale(request):
    sales = Sale.objects.filter(branch = request.user.branch)
    return render(request, 'finance/sales.html', 
        {
            'sales':sales
        }    
    )
 
# @admin_required
@login_required   
def finance(request):
    sales = Sale.objects.filter(date__month = get_current_month(), void=False, branch = request.user.branch).order_by('-date')[:8]
    expenses = Expense.objects.filter(date__month = get_current_month(), branch = request.user.branch).order_by('-date')[:8]
    current_month = get_current_month()

    sales = Sale.objects.filter(date__month = current_month, staff=False, void=False, branch = request.user.branch)
    cogs = COGS.objects.filter(date__month = current_month, production__branch = request.user.branch)
    
    return render(request, 'finance/finance.html', 
        {
            'sales':sales,
            'expenses':expenses,
        }
    )
 
 
@login_required   
def get_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, branch=request.user.branch)
    data = {
        'id': expense.id,
        'amount': expense.amount,
        'description': expense.description,
        'category': expense.category.id,
        'branch_name': expense.branch.branch_name,
        'branch_id':expense.branch.id
    }
    return JsonResponse({'success': True, 'data': data})


@transaction.atomic #use with atomic
@login_required
def expenses(request):
    form = ExpensesForm()
    cat_form = ExpenseCategoryForm()

    if request.method == 'GET':
        filter_option = request.GET.get('filter', 'today')
        download = request.GET.get('download')
        
        now = datetime.datetime.now()
        end_date = now
        
        if filter_option == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif filter_option == 'this_week':
            start_date = now - timedelta(days=now.weekday())
        elif filter_option == 'yesterday':
            start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif filter_option == 'this_month':
            start_date = now.replace(day=1)
        elif filter_option == 'last_month':
            start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        elif filter_option == 'this_year':
            start_date = now.replace(month=1, day=1)
        elif filter_option == 'custom':
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        else:
            start_date = now - - timedelta(days=now.weekday())
            end_date = now
            
        expenses = Expense.objects.filter(date__gte=start_date, date__lte=end_date, branch = request.user.branch).order_by('date')
        
        if download:
            logger.info('download')
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="expenses_report_{filter_option}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Date', 'Description', 'Done By', 'Amount'])

            total_expense = 0  
            for expense in expenses:
                total_expense += expense.amount

                writer.writerow([
                    expense.date,
                    expense.description,
                    expense.user.first_name,
                    expense.amount,
                ])

            writer.writerow(['Total', '', '', total_expense])
            
            return response
        
        return render(request, 'finance/expenses.html', 
            {
                'form':form,
                'cat_form':cat_form,
                'expenses':expenses,
                'filter_option': filter_option,
            }
        )
    
    if request.method == 'POST':
        #payload
        """
            {
                amount:float
                description:str
                category:id (int)
            }
        """
        try:
            data = json.loads(request.body)
            
            amount = Decimal(data.get('amount'))
            description = data.get('description')
            category = data.get('category')
            
            if not amount or not category:
                return JsonResponse({'success':False, 'message':'Missing fields: amount, description, category.'})
            
            try:
                category = ExpenseCategory.objects.get(id=category)
            except ExpenseCategory.DoesNotExist:
                return JsonResponse({'success':False, 'message':f'Category with ID: {category}, doesn\'t exists.'})
           
            expense = Expense.objects.create(
                amount = amount,
                category = category,
                user = request.user,
                cancel = False,
                description = description,
                status = True,
                branch = request.user.branch
            )
            if data.get('debit') == 'True':
                cashier_expenses_update = CashierExpense.objects.get(id = data.get('expense'), branch = request.user.branch)
                if cashier_expenses_update.track_amount < amount:
                    return JsonResponse({'success': False, 'message': 'approoved amount is greater than amount left'}, status = 400)
                else:
                    cashier_expenses_update.track_amount = cashier_expenses_update.track_amount - amount
                    if cashier_expenses_update.track_amount == 0:
                        cashier_expenses_update.status = True
                    
                    cashier_expenses_update.save()


                CashBook.objects.create(
                    amount = amount,
                    expense = expense,
                    credit = True,
                    description=f'Expense ({expense.description[:20]})',
                    branch = request.user.branch
                )
            else:
                CashBook.objects.create(
                    amount = amount,
                    expense = expense,
                    credit = True,
                    description=f'Expense ({expense.description[:20]})',
                    branch = request.user.branch
                )

            send_expense_creation_notification(expense.id)
                
            return JsonResponse({'success': True, 'messages':'Expense successfully created'}, status=201)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

@admin_required
@login_required
@login_required
def add_or_edit_expense(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            amount = data.get('amount')
            description = data.get('description')
            category_id = data.get('category')
            expense_id = data.get('id')

            if not amount or not description or not category_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Missing fields: amount, description, category.'
                }, status=400)

            category = get_object_or_404(ExpenseCategory, id=category_id)

            if expense_id:
                # Update existing expense
                expense = get_object_or_404(Expense, id=expense_id)
                before_amount = expense.amount

                expense.amount = amount
                expense.description = description
                expense.category = category
                expense.save()
                message = 'Expense successfully updated'

                try:
                    cashbook_expense = CashBook.objects.get(expense=expense)
                    expense_amount = Decimal(expense.amount)
                    if cashbook_expense.amount < expense_amount:
                        cashbook_expense.amount = expense_amount
                        cashbook_expense.description += f' Expense (update from {before_amount} to {cashbook_expense.amount})'
                    else:
                        cashbook_expense.amount -= cashbook_expense.amount - expense_amount
                        cashbook_expense.description += f' (update from {before_amount} to {cashbook_expense.amount})'
                    cashbook_expense.save()
                except Exception as e:
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
            else:
                # Create new expense
                expense = Expense.objects.create(
                    amount=amount,
                    description=description,
                    category=category
                )
                message = 'Expense successfully created'

            return JsonResponse({'success': True, 'message': message}, status=201)

        except Exception as e:
            # Debugging line
            print("DEBUG ERROR:", str(e))
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)


@login_required
@transaction.atomic
def delete_expense(request, expense_id):
    if request.method == 'DELETE':
        try:
            expense = get_object_or_404(Expense, id=expense_id, branch=request.user.branch)
            expense.cancel = True
            expense.save()
            
            CashBook.objects.create(
                amount=expense.amount,
                debit=True,
                credit=False,
                description=f'Expense ({expense.description}): cancelled',
                branch=request.user.branch
            )
            return JsonResponse({'success': True, 'message': 'Expense successfully deleted'})
        except Exception as e:
             return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)


@login_required
def cashbook(request):
    filter_option = request.GET.get('filter', 'today')
    now = datetime.datetime.now()
    end_date = now
    
    if filter_option == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_week':
        start_date = now - timedelta(days=now.weekday())
    elif filter_option == 'yesterday':
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_month':
        start_date = now.replace(day=1)
    elif filter_option == 'last_month':
        start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif filter_option == 'this_year':
        start_date = now.replace(month=1, day=1)
    elif filter_option == 'custom':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    else:
        start_date = now - timedelta(days=now.weekday())
        end_date = now

    entries = CashBook.objects.filter(date__gte=start_date, date__lte=end_date, branch=request.user.branch).order_by('date')
    
    total_debit = entries.filter(debit=True).aggregate(Sum('amount'))['amount__sum'] or 0
    total_credit = entries.filter(credit=True).aggregate(Sum('amount'))['amount__sum'] or 0
    
    balance_bf = 0 
    
    previous_entries = CashBook.objects.filter(date__lt=start_date)
    previous_debit = previous_entries.filter(debit=True).aggregate(Sum('amount'))['amount__sum'] or 0
    previous_credit = previous_entries.filter(credit=True).aggregate(Sum('amount'))['amount__sum'] or 0
    balance_bf = previous_debit - previous_credit

    total_balance = balance_bf + (total_debit - total_credit)
    
    sales = SaleItem.objects.filter(sale__void=False)

    return render(request, 'finance/cashbook.html', {
        'filter_option': filter_option,
        'entries': entries,
        'balance_bf': balance_bf,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'total_balance': total_balance,
        'end_date':end_date,
        'start_date':start_date,
        'sales':sales
    })

@login_required
def cashbook_note(request):
    #payload
    """
        entry_id:id,
        note:str
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entry_id = data.get('entry_id')
            note = data.get('note')
            
            entry = CashBook.objects.get(id=entry_id, branch=request.user.branch)
            entry.note = note
            
            entry.save()
        except Exception as e:
            return JsonResponse({'success':False, 'message':f'{e}.'}, status=400)
        return JsonResponse({'success':False, 'message':'Note successfully saved.'}, status=201)
    return JsonResponse({'success':False, 'message':'Invalid request.'}, status=405)

@login_required
def cashbook_note_view(request, entry_id):
    entry = get_object_or_404(CashBook, id=entry_id, branch=request.user.branch)
    
    if request.method == 'GET':
        notes = entry.notes.all().order_by('timestamp')
        notes_data = [
            {'user': note.user.username, 'note': note.note, 'timestamp': note.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
            for note in notes
        ]
        return JsonResponse({'success': True, 'notes': notes_data})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            note_text = data.get('note')
            CashBookNote.objects.create(entry=entry, user=request.user, note=note_text, entry__branch=request.user.branch)
            return JsonResponse({'success': True, 'message': 'Note successfully added.'}, status=201)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=405)
    
@login_required
def cancel_transaction(request):
    #payload
    """
        entry_id:id,
    """
    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')
        
        logger.info(entry_id)
        
        entry = CashBook.objects.get(id=entry_id, branch=request.user.branch)
        
        logger.info(entry)
        entry.cancelled = True
        
        if entry.director:
            entry.director = False
        elif entry.manager:
            entry.manager = False
        elif entry.accountant:
            entry.accountant = False
            
        entry.save()
        
        return JsonResponse({'success': True}, status=201)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
@login_required
def download_cashbook_report(request):
    filter_option = request.GET.get('filter', 'this_week')
    now = datetime.datetime.now()
    end_date = now
    
    if filter_option == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_week':
        start_date = now - timedelta(days=now.weekday())
    elif filter_option == 'yesterday':
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_month':
        start_date = now.replace(day=1)
    elif filter_option == 'last_month':
        start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif filter_option == 'this_year':
        start_date = now.replace(month=1, day=1)
    elif filter_option == 'custom':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    else:
        start_date = now - timedelta(days=now.weekday())
        end_date = now

    entries = CashBook.objects.filter(date__gte=start_date, date__lte=end_date, branch=request.user.branch).order_by('date')

    # Create a CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cashbook_report_{filter_option}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Description', 'Expenses', 'Income', 'Balance'])

    balance = 0  
    for entry in entries:
        if entry.debit:
            balance += entry.amount
        elif entry.credit:
            balance -= entry.amount

        writer.writerow([
            entry.date,
            entry.description,
            entry.amount if entry.debit else '',
            entry.amount if entry.credit else '',
            balance,
            entry.accountant,
            entry.manager,
            entry.director
        ])

    return response


@login_required
def add_expense_category(request):
    categories = ExpenseCategory.objects.all().values()
    
    if request.method == 'POST':
        data = json.loads(request.body)
        category = data['name']
        logger.info(data)
        
        if ExpenseCategory.objects.filter(name=category).exists():
            return JsonResponse({'success':False, 'message':f'Category with ID {category} Exists.'}, status=400)
        
        ExpenseCategory.objects.create(
            name=category
        )
        return JsonResponse({'success':True}, status=201)
    return JsonResponse(list(categories), safe=False)


@login_required
def income_json(request):
    current_month = get_current_month()
    today = datetime.date.today()
    
    month = request.GET.get('month', current_month)
    day = request.GET.get('day', today.day)
    
    if request.GET.get('filter') == 'today':
        sales_total = Sale.objects.filter(date=today, void=False, branch=request.user.branch).aggregate(Sum('total_amount'))
    else:
        sales_total = Sale.objects.filter(date__month=month, void=False, branch=request.user.branch).aggregate(Sum('total_amount'))
    
    logger.info(f'Sales: {sales_total}')
    return JsonResponse({'sales_total': sales_total['total_amount__sum'] or 0})


@login_required
def expense_json(request):
    current_month = get_current_month()
    today = datetime.date.today()
    
    month = request.GET.get('month', current_month)
    day = request.GET.get('day', today.day)
    
    if request.GET.get('filter') == 'today':
        expense_total = Expense.objects.filter(date=today, cancel=False, branch=request.user.branch).aggregate(Sum('amount'))
    else:
        expense_total = Expense.objects.filter(date__month=month, cancel=False, branch=request.user.branch).aggregate(Sum('amount'))
    
    
    return JsonResponse({'expense_total': expense_total['amount__sum'] or 0})


def income_graph(request):
    current_year = get_current_year()
    monthly_sales = Sale.objects.filter(date__year=current_year, void=False, branch=request.user.branch).values('date__month').annotate(total=Sum('total_amount')).order_by('date__month')
    data = {month['date__month']: month['total'] for month in monthly_sales}
    return JsonResponse(data)


@login_required
def expense_graph(request):
    current_year = get_current_year()
    monthly_expenses = Expense.objects.filter(date__year=current_year, branch=request.user.branch).values('date__month').annotate(total=Sum('amount')).order_by('date__month')
    data = {month['date__month']: month['total'] for month in monthly_expenses}
    return JsonResponse(data)



@login_required
def calculate_percentage_change(current_value, previous_value):
    if previous_value == 0:
        return 0 if current_value == 0 else 100
    return ((current_value - previous_value) / previous_value) * 100

@login_required
def cogs_list(request):
    cogs = COGS.objects.filter(production__branch=request.user.branch)
    return render(request, 'finance/cogs.html', {'cogs':cogs})


# @login_required
def pl_overview(request):
    filter_option = request.GET.get('filter')
    today = datetime.date.today()
    previous_month = get_previous_month()
    current_year = today.year
    current_month = today.month

    if filter_option == 'today':
        date_filter = today
    elif filter_option == 'last_week':
        last_week_start = today - datetime.timedelta(days=today.weekday() + 7)
        last_week_end = last_week_start + datetime.timedelta(days=6)
        date_filter = (last_week_start, last_week_end)
    elif filter_option == 'this_month':
        date_filter = (datetime.date(current_year, current_month, 1), today)
    elif filter_option == 'year':
        year = int(request.GET.get('year', current_year))
        date_filter = (datetime.date(year, 1, 1), datetime.date(year, 12, 31))
    else:
        date_filter = (datetime.date(current_year, current_month, 1), today)

    if filter_option == 'today':
        current_month_sales = Sale.objects.filter(date=date_filter, void=False, branch=request.user.branch).aggregate(total_sales=Sum('total_amount'))['total_sales'] or 0
        current_month_expenses = Expense.objects.filter(date=date_filter, cancel=False, branch=request.user.branch).aggregate(total_expenses=Sum('amount'))['total_expenses'] or 0
        cogs_total = COGS.objects.filter(date=date_filter, production__branch=request.user.branch).aggregate(total_cogs=Sum('amount'))['total_cogs'] or 0
    elif filter_option == 'last_week':
        current_month_sales = Sale.objects.filter(date__range=date_filter, void=False, branch=request.user.branch).aggregate(total_sales=Sum('total_amount'))['total_sales'] or 0
        current_month_expenses = Expense.objects.filter(date__range=date_filter, cancel=False, branch=request.user.branch).aggregate(total_expenses=Sum('amount'))['total_expenses'] or 0
        cogs_total = COGS.objects.filter(date__range=date_filter, production__branch=request.user.branch).aggregate(total_cogs=Sum('amount'))['total_cogs'] or 0
    else:
        current_month_sales = Sale.objects.filter(date__range=date_filter, void=False, branch=request.user.branch).aggregate(total_sales=Sum('total_amount'))['total_sales'] or 0
        current_month_expenses = Expense.objects.filter(date__range=date_filter, cancel=False, branch=request.user.branch).aggregate(total_expenses=Sum('amount'))['total_expenses'] or 0
        cogs_total = COGS.objects.filter(date__range=date_filter, production__branch=request.user.branch).aggregate(total_cogs=Sum('amount'))['total_cogs'] or 0

    previous_month_sales = Sale.objects.filter(date__year=current_year, date__month=previous_month, void=False, branch=request.user.branch).aggregate(total_sales=Sum('total_amount'))['total_sales'] or 0
    previous_month_expenses = Expense.objects.filter(date__year=current_year, date__month=previous_month, cancel=False, branch=request.user.branch).aggregate(total_expenses=Sum('amount'))['total_expenses'] or 0
    previous_cogs =  COGS.objects.filter(date__year=current_year, date__month=previous_month, production__branch=request.user.branch).aggregate(total_cogs=Sum('amount'))['total_cogs'] or 0
    
    current_net_income = current_month_sales
    previous_net_income = previous_month_sales 
    current_expenses = current_month_expenses 
    
    current_gross_profit = current_month_sales - cogs_total
    previous_gross_profit = previous_month_sales - previous_cogs
    
    current_net_profit = current_gross_profit - current_month_expenses
    previous_net_profit = previous_gross_profit - previous_month_expenses

    current_gross_profit_margin = (current_gross_profit / current_month_sales * 100) if current_month_sales != 0 else 0
    previous_gross_profit_margin = (previous_gross_profit / previous_month_sales * 100) if previous_month_sales != 0 else 0
    
    # net_income_change = calculate_percentage_change(current_net_income, previous_net_income)
    # gross_profit_change = calculate_percentage_change(current_gross_profit, previous_gross_profit)
    # gross_profit_margin_change = calculate_percentage_change(current_gross_profit_margin, previous_gross_profit_margin)


    data = {
        'net_profit':current_net_profit,
        'cogs_total':cogs_total,
        'current_expenses':current_expenses,
        'current_net_profit': current_net_profit,
        'previous_net_profit':previous_net_profit,
        'current_net_income': current_net_income,
        'previous_net_income': previous_net_income,
        'current_gross_profit': current_gross_profit,
        'previous_gross_profit': previous_gross_profit,
        'current_gross_profit_margin': f'{current_gross_profit_margin:.2f}',
        'previous_gross_profit_margin': previous_gross_profit_margin,
    }
    
    return JsonResponse(data)


@login_required
def generate_report(request):
    time_frame = request.GET.get('timeFrame')
    start_date = None
    end_date = None

    if time_frame == 'today':
        start_date = end_date = datetime.datetime.today()
    elif time_frame == 'weekly':
        start_date = datetime.datetime.today()- timedelta(days=7)
        end_date = datetime.datetime.today()
    elif time_frame == 'monthly':
        start_date = datetime.datetime.today() - timedelta(days=30)
        end_date = datetime.datetime.today()
    elif time_frame == 'yearly':
        start_date = datetime.datetime.today() - timedelta(days=365)
        end_date = datetime.datetime.today()
    elif time_frame == 'custom':
        start_date = datetime.datetime.strptime(request.GET.get('startDate'), '%Y-%m-%d')
        end_date = datetime.datetime.strptime(request.GET.get('endDate'), '%Y-%m-%d')

    sales_total = Sale.objects.filter(date__range=(start_date, end_date), void=False, branch=request.user.branch).aggregate(total_sales=Sum('total_amount'))['total_sales'] or 0
    expenses_total = Expense.objects.filter(date__range=(start_date, end_date), cancel=False, branch=request.user.branch).aggregate(total_expenses=Sum('amount'))['total_expenses'] or 0
    cogs_total = COGS.objects.filter(date__range=(start_date, end_date), production__branch=request.user.branch).aggregate(total_cogs=Sum('amount'))['total_cogs'] or 0
    net_profit = sales_total - expenses_total - cogs_total
    gross_profit = sales_total - cogs_total

    context = {
        # 'user':request.user,
        'sales_total': sales_total,
        'expenses_total': expenses_total,
        'cogs_total': cogs_total,
        'net_profit': net_profit,
        'time_frame': time_frame,
        'start_date': start_date,
        'end_date': end_date,
        'gross_profit': gross_profit
    }

    html_string = render_to_string('finance/income_statement_template.html', context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="income_statement_{time_frame}.pdf"'
    pisa_status = pisa.CreatePDF(html_string, dest=response)

    if pisa_status.err:
        logger.info('We had some errors with generating the report')
        return HttpResponse('We had some errors with generating the report')
    
    return response
 
@login_required
def cash_up(request):
    if request.method == 'GET':
        form = CashUpForm()
        
        filter_option = request.GET.get('filter', 'today')
        download = request.GET.get('download')
        
        now = datetime.datetime.now()
        end_date = now
        
        if filter_option == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif filter_option == 'this_week':
            start_date = now - timedelta(days=now.weekday())
        elif filter_option == 'yesterday':
            start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif filter_option == 'this_month':
            start_date = now.replace(day=1)
        elif filter_option == 'last_month':
            start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        elif filter_option == 'this_year':
            start_date = now.replace(month=1, day=1)
        elif filter_option == 'custom':
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        else:
            start_date = now - - timedelta(days=now.weekday())
            end_date = now
            
        cashups = CashUp.objects.filter(date__gte=start_date, date__lte=end_date, branch=request.user.branch).order_by('date')
        
        if download:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="cashups_report_{filter_option}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Date', 'Cashier', 'Done By', 'Sales' 'Cashed Amount', 'status'])

            for cashup in cashups:
                writer.writerow([
                    cashup.date,
                    cashup.cashier.first_name,
                    cashup.user.first_name,
                    cashup.sales,
                    'Done' if cashup.status else 'Not done'
                ])
            
            return response
        return render(request, 'finance/cashups.html', 
            {
                'form':form, 
                'cashups':cashups, 
                'filter_option':filter_option
            }
        )
    
    if request.method == 'POST':
        # payload
        """
            {
              cashier:id,
              cashed_amount:float,  
            } 
        """
        from inventory.models import EndOfDay, EndOfDayCashier
        
        try:
            data = json.loads(request.body)
            cashed_amount = float(data.get('cashed_amount'))
            cashier = int(data.get('cashier'))
            
            if cashed_amount < 0:
                return JsonResponse({'success':False, 'message':f'Cashed amount cannot be less than zero.'}, status=400)
            
            with transaction.atomic():
                cash_up = CashUp.objects.get(cashier__id=cashier, cashed=False, branch=request.user.branch)
                cash_up.cashed_amount = Decimal(cashed_amount)

                cash_up.difference = cash_up.cashed_amount - (cash_up.sales - cash_up.void_amount - cash_up.expenses + cash_up.change)
                cash_up.cashed = True
                
                end_of_day = EndOfDay.objects.filter(branch=request.user.branch, date=cash_up.date).first()
                
                logger.info(f' End of day: {end_of_day}')
                
                sales = calculate_cashier_sales(cash_up.cashier, cash_up.date, request.user.branch)
                expense = calculate_cashier_expenses(cash_up.cashier, cash_up.date, request.user.branch)
                
                logger.info(f'sales {sales}')
                
                EndOfDayCashier.objects.create(
                    end_of_day = end_of_day,
                    cashier = cash_up.cashier,
                    cashed_amount = Decimal(cashed_amount),
                    sales = sales['normal_sales'],
                    voids = sales['void_sales'],
                    expenses = expense['expenses_total'],
                    variance = Decimal(sales['normal_sales']) - Decimal(cashed_amount)
                )
        
                end_of_day.save()
                cash_up.save()
                logger.success(f'Cash up recorded successfully!')
        except Exception as e:
            logger.error(f'Error processing cashup {e}')
            return JsonResponse({'success':False, 'message':f'{e}'}, status=400)
        return JsonResponse({'success':True, 'message':f'Cash Up successfully created'}, status=201)
    return JsonResponse({'success':False, 'message':f'Invalid request'}, status=405)

@login_required
@transaction.atomic
def claim_cashup_difference(request, cashup_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cashup_id = data.get('cashup_id')
            claim_amount = data.get('claim_amount')

            cash_up = CashUp.objects.select_for_update().get(id=cashup_id, branch=request.user.branch)
            
            if cash_up.status:
                return JsonResponse({'success': False, 'message': f'Cash up already processed'}, status=400)
            
            cash_up.status = True
            cash_up.save()

            CashBook.objects.create(
                amount=claim_amount,
                debit=True,
                credit=False,
                description='Over cash up claim',
                branch=request.user.branch
            )

        except Exception as e:
            return JsonResponse({'success': False, 'message': f'{e}'}, status=400)
        return JsonResponse({'success': True, 'message': 'Cash Up successfully claimed'}, status=201)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

@login_required
@transaction.atomic
def charge_cashup_difference(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cashup_id = data.get('cashup_id')
            charge_amount = data.get('charge_amount')

            logger.info(charge_amount)
            cash_up = CashUp.objects.select_for_update().get(id=cashup_id, branch=request.user.branch)
            
            if cash_up.status:
                return JsonResponse({'success': False, 'message': f'Cash up already processed'}, status=400)
            
            cash_up.status = True
            cash_up.save()

            CashierAccount.objects.create(
                cashier = cash_up.cashier,
                cash_up = cash_up,
                amount=charge_amount,
                status = False,
                branch=request.user.branch
            )

        except Exception as e:
            return JsonResponse({'success': False, 'message': f'{e}'}, status=400)
        return JsonResponse({'success': True, 'message': 'Cash Up successfully claimed'}, status=201)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

@login_required
def cashiers_list(request):
    
    if request.method == 'GET':
        cashiers = CashierAccount.objects.filter(branch=request.user.branch)
        logger.info(cashiers)
        return render(request, 'finance/cashiers.html', {'cashiers':cashiers})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cashier_id = data.get('cashier_id')
            amount = Decimal(data.get('amount'))
            
            cashier = CashierAccount.objects.get(id=cashier_id, branch=request.user.branch)
            cashups = CashUp.objects.filter(cashier=cashier.cashier, branch=request.user.branch).order_by('-id')
            
            for cashup in cashups:
                outstanding_balance = cashup.sales - cashup.cashed_amount
                
                if amount >= outstanding_balance:
                    # If the amount is enough to cover this cashup entry, reduce the amount
                    amount -= outstanding_balance
                    cashup.cashed_amount += outstanding_balance
                    cashup.save()
                    
                    if amount == 0:
                        break
                else:
                    # If the amount is not enough to cover this entry completely, deplete it and stop
                    cashup.cashed_amount += amount
                    amount = 0
                    cashup.save()
                    break
            
            # Check if all cashups are fully paid
            all_paid = all((cu.sales == cu.cashed_amount) for cu in cashups)
            if all_paid:
                cashier.status = True
                cashier.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

@login_required
def update_transaction_status(request, pk):
    if request.method == 'POST':
        entry = get_object_or_404(CashBook, pk=pk, branch=request.user.branch)
        
        data = json.loads(request.body)
        
        status = data.get('status')
        field = data.get('field')  

        if field in ['manager', 'accountant', 'director']:
            setattr(entry, field, status)

            if entry.cancelled:
                entry.cancelled = False
            entry.save()
            return JsonResponse({'success': True, 'status': getattr(entry, field)})
        
    return JsonResponse({'success': False}, status=400)

@login_required
def update_expense_status(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            expense_id = data.get('id')
            status = data.get('status')

            expense = Expense.objects.get(id=expense_id, branch=request.user.branch)
            expense.status = status
            expense.save()

            return JsonResponse({'success': True, 'message': 'Status updated successfully.'})
        except Expense.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Expense not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def days_data(request):
    from datetime import date, timedelta
    from calendar import monthrange
    from django.db.models import Sum


    today = date.today()
    current_month = today.month
    year = today.year

    sales = Sale.objects.filter(date__month=current_month, staff=False, void=False, branch=request.user.branch)
    cogs = COGS.objects.filter(date__month=current_month, production__branch=request.user.branch)

    first_day = date(year, current_month, 1)
    _, last_day = monthrange(year, current_month)
    num_weeks = ((last_day - 1) // 7) + 1  # ensures full coverage

    def get_week_data(queryset, start_date, end_date, amount_field):
        week_data = queryset.filter(date__gte=start_date, date__lt=end_date).values(amount_field, 'date')
        total = week_data.aggregate(total=Sum(amount_field))['total'] or 0
        return week_data, total

    data = {}
    for week in range(1, num_weeks + 1):
        week_start = first_day + timedelta(days=(week - 1) * 7)
        week_end = min(week_start + timedelta(days=7), date(year, current_month, last_day) + timedelta(days=1))
        
        sales_data, sales_total = get_week_data(sales, week_start, week_end, 'total_amount')
        cogs_data, cogs_total = get_week_data(cogs, week_start, week_end, 'amount')
        
        data[f'week {week}'] = {
            'sales': list(sales_data),
            'cogs': list(cogs_data),
            'total_sales': sales_total,
            'total_cogs': cogs_total
        }
    
    return JsonResponse(data)

@login_required
def transaction_logs(request):
    """Transaction logs with date filters and pagination (supports JSON for infinite scroll)."""
    filter_option = request.GET.get('filter', 'today')
    start_date_param = request.GET.get('start_date')
    end_date_param = request.GET.get('end_date')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 30))
    fmt = request.GET.get('format') 

    now = datetime.datetime.now()
    end_date = now

    if filter_option == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_week':
        start_date = now - timedelta(days=now.weekday())
    elif filter_option == 'yesterday':
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_option == 'this_month':
        start_date = now.replace(day=1)
    elif filter_option == 'last_month':
        start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        end_date = (now.replace(day=1) - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)
    elif filter_option == 'this_year':
        start_date = now.replace(month=1, day=1)
    elif filter_option == 'custom' and start_date_param and end_date_param:
        start_date = datetime.datetime.strptime(start_date_param, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date_param, '%Y-%m-%d')
    else:
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now

    qs = Logs.objects.select_related('sale', 'user').filter(
        sale__date__gte=start_date.date(),
        sale__date__lte=end_date.date(),
        sale__branch=request.user.branch
    ).order_by('-timestamp')
    
    print('transactions', qs)

    total_count = qs.count()
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    page_qs = qs[start_index:end_index]
    has_next = end_index < total_count

    sale_ids = [log.sale_id for log in page_qs if log.sale_id]
    sale_items_qs = SaleItem.objects.select_related('sale', 'meal', 'dish', 'product').filter(
        sale_id__in=sale_ids,
        sale__branch=request.user.branch
    )
    sale_id_to_items = {}
    for si in sale_items_qs:
        label = None
        if getattr(si, 'meal_id', None):
            label = f"{si.meal} x {si.quantity}"
        elif getattr(si, 'dish_id', None):
            label = f"{si.dish} x {si.quantity}"
        elif getattr(si, 'product_id', None):
            label = f"{si.product.name} x {si.quantity}"
        if label:
            sale_id_to_items.setdefault(si.sale_id, []).append(label)

    if fmt == 'json':
        items = []
        for log in page_qs:
            if not log.sale_id:
                continue
            items.append({
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(log.timestamp, 'strftime') else str(log.timestamp),
                'cashier': getattr(getattr(log, 'user', None), 'username', ''),
                'receipt_number': getattr(log.sale, 'receipt_number', ''),
                'products': sale_id_to_items.get(log.sale_id, []),
                'total_amount': str(getattr(log.sale, 'total_amount', '')),
                'change': str(getattr(log.sale, 'change', '')),
            })
        return JsonResponse({'success': True, 'items': items, 'has_next': has_next, 'next_page': page + 1 if has_next else None})
    
    print(page_qs)

    context = {
        'transactions': page_qs,
        'sale_items': sale_items_qs,
        'has_next': has_next,
        'page_size': page_size,
        'filter_option': filter_option,
        'start_date': start_date.date(),
        'end_date': end_date.date(),
    }
    return render(request, 'transaction_logs.html', context)

@login_required
def cashier_expenses(request, cashier_id):
    if request.method == 'GET':
        expense_category = ExpenseCategory.objects.all()

        if request.user.role in ['manager', 'supervisor', 'admin', 'accountant']:
            expenses = CashierExpense.objects.select_related('cashier').filter(branch=request.user.branch)
        else:
            expenses = CashierExpense.objects.select_related('cashier').filter(cashier__id=cashier_id, branch=request.user.branch)

        grouped_expenses = defaultdict(list)
        for expense in expenses.order_by('-date'):
            grouped_expenses[expense.date].append(expense)

        
        total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0

        logger.info(grouped_expenses)
        print(type(grouped_expenses))

        grouped_expense = dict(grouped_expenses)

        return render(request, 'finance/cashier_expenses.html', {
            'grouped_expenses': grouped_expense,
            'categories': expense_category,
            'total_expenses': total_expenses
        })
    
    if request.method == 'POST':
        """
            name:str
            amount:float,
            description:str,
        """
        data = json.loads(request.body)
        name = data.get('name')
        amount = data.get('amount')
        description = data.get('description')
        
        if not name:
            return JsonResponse({'success':False, 'message':'Missing fields: name.'})
        
        if not amount:
            return JsonResponse({'success':False, 'message':'Missing fields: amount.'})
        
        CashierExpense.objects.create(
            name=name,
            amount=amount,
            track_amount = amount,
            description=description,
            cashier=request.user,
            status = False,
            branch=request.user.branch
        )
        
        return JsonResponse({'success':True, 'message':'Cashier expense successfully created.'}, status=201)
    
    if request.method == 'PUT':
        """
            expense_id:int
        """
        data = json.loads(request.body)
        logger.info(data)
        expense_id = data.get('expense_id')
        name = data.get('name')
        amount = float(data.get('amount'))
        description = data.get('description')

        logger.info(type(amount))
        try:
            expense = CashierExpense.objects.get(id=expense_id, branch=request.user.branch)
            
            expense.name = name
            expense.amount = amount
            expense.track_amount = amount
            expense.description = description
        
            expense.save()
            return JsonResponse({'success':True, 'message':'Cashier expense successfully updated.'}, status=201)
        except CashierExpense.DoesNotExist:
            return JsonResponse({'success':False, 'message':'Cashier expense not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success':False, 'message':f'{e}.'}, status=500)
        

    if request.method == 'DELETE':
        """
            expense_id:int
        """
        data = json.loads(request.body)
        expense_id = data.get('expense_id')
        
        try:
            expense = CashierExpense.objects.get(id=expense_id, branch=request.user.branch)
            expense.delete()
            return JsonResponse({'success':True, 'message':'Cashier expense successfully updated.'}, status=201)
        except CashierExpense.DoesNotExist:
            return JsonResponse({'success':False, 'message':'Cashier expense not found.'}, status=404)

    
    return JsonResponse({'success':False, 'message':'Invalid request method.'}, status=405)


@login_required
def cashier_report_form(request):
    """Display form to select cashier and date"""
    cashiers = User.objects.filter().order_by('username')

    context = {
        'cashiers': cashiers,
        'today': datetime.date.today(),
    }
    return render(request, 'finance/cashier_report.html', context)


@login_required
def cash_up(request, cashier_id):
    """Generate cash up report for specified cashier and date"""
    logger.info(f'Cash up requested for cashier_id: {cashier_id} by user: {request.user.username}')
    
    if request.method == 'GET':
        try:
            report_date_str = request.GET.get('date')
            if report_date_str:
                report_date = datetime.datetime.strptime(report_date_str, '%Y-%m-%d').date()
            else:
                report_date = datetime.date.today()
            
            report_type = request.GET.get('report_type', 'cash_up')
            
            logger.info(f'Generating {report_type} report for date: {report_date}')
            
            # Validate cashier_id
            try:
                cashier = User.objects.get(id=cashier_id)
                logger.info(f'Found cashier: {cashier.username}')
            except User.DoesNotExist:
                logger.error(f'Cashier with id {cashier_id} does not exist')
                return JsonResponse({'success': False, 'message': 'Cashier not found'}, status=404)
                
            if not request.user.branch:
                logger.error('Request user has no branch assigned')
                return JsonResponse({'success': False, 'message': 'User has no branch assigned'}, status=400)

            # Get base sales data
            sales = Sale.objects.filter(
                cashier__id=cashier_id, 
                date=report_date, 
                void=False, 
                branch=request.user.branch
            ).values('id', 'total_amount', 'cash_type', 'staff', 'date')
            
            sales_items = SaleItem.objects.filter(
                sale__cashier__id=cashier_id, 
                sale__date=report_date, 
                sale__branch=request.user.branch
            ).select_related('sale', 'dish', 'product', 'meal')
            
            void_sales = Sale.objects.filter(
                cashier__id=cashier_id, 
                date=report_date, 
                void=True, 
                branch=request.user.branch
            ).values('total_amount')

            # Prepare base data structures
            sales_dict = {}
            staff_meals_dict = {}
            void_sales_dict = {}
            total_summary_sales = 0
            total_staff_summary_sales = 0
            sales_summary = defaultdict(lambda: {'price': 0, 'quantity':0})
            staff_sales_summary = defaultdict(lambda: {'price': 0, 'quantity':0})
        
            # Build sales summaries
            for sale in sales_items.filter(sale__staff=False):
                item = sale.meal or sale.product or sale.dish
                if item:
                    key = f"{item.name}"
                    sales_summary[key]['price'] = round(sale.price, 2)
                    sales_summary[key]['quantity'] += sale.quantity
                    total_summary_sales += round(sale.price * sale.quantity, 2)
            
            for sale in sales_items.filter(sale__staff=True):
                item = sale.meal or sale.product or sale.dish
                if item:
                    key = f"{item.name}"
                    staff_sales_summary[key]['price'] = round(sale.price, 2)
                    staff_sales_summary[key]['quantity'] += sale.quantity
                    total_staff_summary_sales += round(sale.price * sale.quantity, 2)

            # Build detailed dictionaries
            for items in sales_items.filter(sale__staff=False):
                if items.dish:
                    name = [{'Name': items.dish.name, 'Price': items.dish.price}]
                elif items.product:
                    name = [{'Name': items.product.name, 'Price': items.product.price}]
                elif items.meal:
                    name = [{'Name': dish.name, 'Price': dish.price} for dish in items.meal.dish.all()]
                else:
                    name = None

                if name:
                    for item in name:
                        dish_name = item['Name']
                        dish_price = item['Price']

                        if not items.sale.void and not items.sale.staff:
                            if dish_name in sales_dict:
                                sales_dict[dish_name]['Quantity'] += items.quantity
                                sales_dict[dish_name]['Total'] += items.quantity * dish_price
                            else:
                                sales_dict[dish_name] = {
                                    'Name': dish_name,
                                    'Quantity': items.quantity,
                                    'Price': dish_price,
                                    'Total': items.quantity * dish_price
                                }
                        elif items.sale.staff:
                            if dish_name in staff_meals_dict:
                                staff_meals_dict[dish_name]['Quantity'] += items.quantity
                                staff_meals_dict[dish_name]['Total'] += items.quantity * dish_price
                            else:
                                staff_meals_dict[dish_name] = {
                                    'Name': dish_name,
                                    'Quantity': items.quantity,
                                    'Price': dish_price,
                                    'Total': items.quantity * dish_price
                                }
                        elif items.sale.void:
                            if dish_name in void_sales_dict:
                                void_sales_dict[dish_name]['Quantity'] += items.quantity
                                void_sales_dict[dish_name]['Total'] += items.quantity * dish_price
                            else:
                                void_sales_dict[dish_name] = {
                                    'Name': dish_name,
                                    'Quantity': items.quantity,
                                    'Price': dish_price,
                                    'Total': items.quantity * dish_price
                                }

            sales_portions_list = list(sales_dict.values())
            staff_meals_portions_list = list(staff_meals_dict.values())
            void_sales_portions_list = list(void_sales_dict.values())
            
            sale_total = sum(item['Total'] for item in sales_portions_list)
            staff_total = sum(item['Total'] for item in staff_meals_portions_list)
            
            # Calculate eco cash
            eco_cash_total = sum(item['total_amount'] for item in sales if item['cash_type'] == 'eco-cash' and not item['staff'])
            eco_cash_tax = 0.00

            # Get expenses
            expenses = CashierExpense.objects.filter(
                cashier__id=cashier_id,
                date=report_date,
                branch=request.user.branch
            )
            
            expenses_list = []
            for item in expenses:
                if item.name:
                    expenses_list.append({
                        'Name': item.name, 
                        'Amount': item.amount,
                        'time': item.created_at.strftime('%H:%M:%S') if hasattr(item, 'created_at') else 'N/A'
                    })
            
            # Calculate totals
            total_sales = sum(sale['total_amount'] for sale in sales if not sale['staff'])
            total_staff_sales = sum(sale['total_amount'] for sale in sales if sale['staff'])
            total_void_sales = sum(void_sale['total_amount'] for void_sale in void_sales)
            total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0

            # Get change information
            accumulated_change = Change.objects.filter(
                cashier__id=cashier_id,
                collected=False,
                timestamp__date=report_date,
                sale__branch=request.user.branch
            )

            collected_changes = Change.objects.filter(
                Q(cashier__id=cashier_id)|
                Q(cashier_give__id=cashier_id),
                timestamp__date=report_date,
                collected=True,
                # data_collected=report_date,
                sale__branch=request.user.branch
            ).exclude(
                cashier__id=cashier_id
            ).aggregate(Sum('amount_collected'))['amount_collected__sum'] or 0

            cashier_partially_collected_changes = Change.objects.filter(
                timestamp__date=report_date,
                cashier__id=cashier_id,
                collected=False,
                balance__gt=0,
                sale__branch=request.user.branch
            ).aggregate(Sum('balance'))['balance__sum'] or 0

            uncollected_change = Change.objects.filter(
                timestamp__date=report_date,
                cashier__id=cashier_id,
                collected=False,
                amount_collected=0,
                sale__branch=request.user.branch
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            total_change = accumulated_change.aggregate(Sum('amount'))['amount__sum'] or 0
            cash_in_hand = total_sales - total_expenses - total_void_sales - collected_changes + uncollected_change + cashier_partially_collected_changes 
            uncollected_change = uncollected_change + cashier_partially_collected_changes

            # Get finished products
            # finished_product = finishedProduct(cashier_id)


            # Only create CashUp record if it's for today
            if report_date == datetime.date.today():
                CashUp.objects.create(
                    branch=request.user.branch,
                    cashier=cashier,
                    void_amount=total_void_sales,
                    sales=total_sales,
                    change=collected_changes + cashier_partially_collected_changes,
                    user=request.user,
                    expenses=total_expenses,
                    status=False,
                    cashed=False,
                )

            # Build base data response
            data = {
                "cashier": cashier.get_full_name() or cashier.username,
                "cashier_name": cashier.get_full_name() or cashier.username,
                "report_date": report_date.strftime('%Y-%m-%d'),
                "total_sales": total_sales,
                'sales_portions': sales_portions_list,
                'void_sales_portions': void_sales_portions_list,
                'staff_meal_portions': staff_meals_portions_list,
                'previous_change_given': [],
                # 'variance': list(eod_list),
                'expense': expenses_list,
                'total_expenses': total_expenses,
                'total_change': round(uncollected_change, 2),
                'total_accumulated_change': uncollected_change,
                'cash_in_hand': round(cash_in_hand, 2),
                'sales_total': sale_total,
                'staff_total': staff_total,
                # 'finished_product': finished_product,
                'sales_summary': sales_summary,
                'total_summary_sales': total_summary_sales,
                'staff_sales_summary': staff_sales_summary,
                'eco_cash_total': eco_cash_total,
                'eco_cash_tax': Decimal(eco_cash_tax),
                'collected_changes': float(collected_changes),
            }

            # Add report-specific data based on report type
            if report_type == 'sales_detail':
                data['sales_detail'] = get_sales_detail(cashier_id, report_date, request.user.branch)
            elif report_type == 'changes_detail':
                data.update(get_changes_detail(cashier_id, report_date, request.user.branch))
            elif report_type == 'staff_meals_detail':
                data['staff_meals_detail'] = get_staff_meals_detail(cashier_id, report_date, request.user.branch)

            return JsonResponse({'success': True, "data": data})
            
        except Exception as e:
            logger.exception('Error in cash_up view')
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred while processing your request',
                'error': str(e)
            }, status=500)

    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


def get_sales_detail(cashier_id, report_date, branch):
    """Get detailed sales information with time and items"""
    sales = Sale.objects.filter(
        cashier__id=cashier_id,
        date=report_date,
        void=False,
        staff=False,
        branch=branch
    ).order_by('date')
    
    sales_detail = []
    for sale in sales:
        sale_items = SaleItem.objects.filter(sale=sale)
        
        items_list = []
        for sale_item in sale_items:
            item = sale_item.meal or sale_item.product or sale_item.dish
            
            if item:
                if sale_item.meal:
                    # For meals, list all dishes
                    for dish in sale_item.meal.dish.all():
                        items_list.append({
                            'name': f"{sale_item.meal.name} ({dish.name})",
                            'quantity': sale_item.quantity,
                            'price': dish.price,
                            'total': dish.price * sale_item.quantity
                        })
                else:
                    items_list.append({
                        'name': item.name,
                        'quantity': sale_item.quantity,
                        'price': sale_item.price,
                        'total': sale_item.price * sale_item.quantity
                    })
        
        sales_detail.append({
            'sale_number': sale.id,
            'time': sale.date.strftime('%H:%M:%S'),
            'total_amount': float(sale.total_amount),
            'cash_type': sale.cash_type,
            'is_staff': sale.staff,
            'items': items_list
        })
    
    return sales_detail


def get_staff_meals_detail(cashier_id, report_date, branch):
    """Get detailed staff meals information"""
    staff_sales = Sale.objects.filter(
        cashier__id=cashier_id,
        date=report_date,
        void=False,
        staff=True,
        branch=branch
    ).order_by('-id')
    
    staff_meals_detail = []
    for sale in staff_sales:
        sale_items = SaleItem.objects.filter(sale=sale)
        
        items_list = []
        for sale_item in sale_items:
            item = sale_item.meal or sale_item.product or sale_item.dish
            
            if item:
                if sale_item.meal:
                    for dish in sale_item.meal.dish.all():
                        items_list.append({
                            'name': f"{sale_item.meal.name} ({dish.name})",
                            'quantity': sale_item.quantity,
                            'price': dish.price,
                            'total': dish.price * sale_item.quantity
                        })
                else:
                    items_list.append({
                        'name': item.name,
                        'quantity': sale_item.quantity,
                        'price': sale_item.price,
                        'total': sale_item.price * sale_item.quantity
                    })
        
        staff_meals_detail.append({
            'time': sale.date.strftime('%H:%M:%S'),
            'total_amount': float(sale.total_amount),
            'items': items_list
        })
    
    return staff_meals_detail


def get_changes_detail(cashier_id, report_date, branch):
    """Get detailed changes information"""
    changes = Change.objects.filter(
        Q(cashier__id=cashier_id)|
        Q(cashier_give__id=cashier_id),
        timestamp__date=report_date,
        # data_collected=report_date,
        sale__branch=branch
    ).order_by('timestamp')
    
    changes_detail = []
    total_given = 0
    total_collected = 0
    total_pending = 0
    
    for change in changes:
        change_data = {
            'id': change.id,
            'name': change.name,
            'time': change.timestamp.strftime('%H:%M:%S'),
            'amount': float(change.amount),
            'amount_collected': float(change.amount_collected or 0),
            'balance': float(change.balance if hasattr(change, 'balance') else change.amount),
            'collected': change.collected,
            'recorded_by':change.cashier.username,
            'issued_by':change.cashier_give.username if change.cashier_give else 'Not yet collected'
        }
        
        if change.collected and hasattr(change, 'data_collected'):
            try:
                collector = User.objects.get(id=change.collected_by_id) if hasattr(change, 'collected_by_id') else None
                change_data['collected_by'] = collector.username if collector else 'N/A'
                change_data['collection_time'] = change.data_collected.strftime('%H:%M:%S') if change.data_collected else 'N/A'
            except:
                change_data['collected_by'] = 'N/A'
                change_data['collection_time'] = 'N/A'
        
        changes_detail.append(change_data)
        
        total_given += float(change.amount)
        if change.collected:
            total_collected += float(change.amount_collected or 0)
        # else:
        #     total_pending += float(change.balance if hasattr(change, 'balance') else change.amount)
    
    return {
        'changes_detail': changes_detail,
        'total_change_given': total_given,
        'total_change_collected': total_collected,
        'total_change_pending': total_pending or 0
    }