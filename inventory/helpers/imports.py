import json
import csv
import io
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.views import View
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.utils.timezone import localdate
from reportlab.lib.pagesizes import A4, letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from utils.email import EmailThread
from django.core.mail import EmailMessage
from finance.models import COGS
from datetime import timedelta, time
import datetime
from .. tasks import inventory_task
from django.db.models import Q
from finance.models import (
    Sale,
    SaleItem,
    Sale,
    SaleItem,
    CashBook,
    Expense, 
    CashUp,
    ExpenseCategory
)
from .. tasks import (
    send_production_creation_notification,
    transfer_notification,
    supplier_email,
    sendProductHistory,
    autoConfirmProdPlan
)
from .. forms import (
    MealForm,
    AddProductForm,
    AddSupplierForm,
    CreateOrderForm,
    noteStatusForm,
    PurchaseOrderStatus,
    UnitOfMeasurementForm,
    EditProductForm,
    ProductionPlanInlineForm,
    DishForm, 
    IngredientForm,
    TransferForm,
    CreateBudgetItemForm,
    CreateStockTakeForm
)
from utils.supplier_best_price import best_price
from utils.utils import render_to_pdf
from permisions.permisions import admin_required, chef_only_required, stores_person_only_required, chef_or_stores_view_required
from loguru import logger
from inventory.models import *
from django.db.models import F, ExpressionWrapper, DecimalField