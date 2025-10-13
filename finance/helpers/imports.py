import csv
from ..models import *
import datetime, json
from loguru import logger
from ..forms import (
    CashUpForm,
    ExpensesForm,
    ExpenseCategoryForm
)
from xhtml2pdf import pisa
from decimal import Decimal
from datetime import  timedelta
from django.db.models import Sum
from django.db import transaction
from ..models import Sale, Expense, CashierPayments
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from ..tasks import send_expense_creation_notification
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from inventory.models import Logs
from permisions.permisions import admin_required
from collections import defaultdict