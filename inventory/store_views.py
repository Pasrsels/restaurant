from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from .models import CheckList, Product
import datetime

@login_required
def store_checklist(request):
    """Store person's checklist view - similar to chef's but with different template"""
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch=request.user.branch)
    non_production_products = Product.objects.filter(raw_material=False, branch=request.user.branch)
    
    check_list = []
    for product in non_production_products:
        if not products.filter(product=product).exists():
            check_list.append(CheckList(
                product=product,
                status=False
            ))
    
    if check_list:
        CheckList.objects.bulk_create(check_list)
    
    products = CheckList.objects.filter(date=datetime.datetime.today(), product__branch=request.user.branch)
    
    return render(request, 'inventory/checklist_store.html', {'products': products})

@login_required
def store_checklist_ajax(request):
    """AJAX version of store_checklist"""
    products = Product.objects.filter(branch=request.user.branch).order_by('name')
    context = {
        'products': products
    }
    return render(request, 'inventory/checklist_store_content.html', context)

@login_required
def store_check_list_finished_products(request):
    """Mark all finished products as checked in the store checklist"""
    try:
        finished_products = Product.objects.filter(
            raw_material=False,
            branch=request.user.branch
        )
        
        for product in finished_products:
            CheckList.objects.update_or_create(
                product=product,
                date=datetime.datetime.today(),
                defaults={'status': True}
            )
            
        return JsonResponse({'success': True, 'message': 'Finished products marked as checked'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
def store_check_list_raw_products(request):
    """Mark all raw materials as checked in the store checklist"""
    try:
        raw_products = Product.objects.filter(
            raw_material=True,
            branch=request.user.branch
        )
        
        for product in raw_products:
            CheckList.objects.update_or_create(
                product=product,
                date=datetime.datetime.today(),
                defaults={'status': True}
            )
            
        return JsonResponse({'success': True, 'message': 'Raw materials marked as checked'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
def store_check_list_all_products(request):
    """Mark all products as checked in the store checklist"""
    try:
        all_products = Product.objects.filter(
            branch=request.user.branch
        )
        
        for product in all_products:
            CheckList.objects.update_or_create(
                product=product,
                date=datetime.datetime.today(),
                defaults={'status': True}
            )
            
        return JsonResponse({'success': True, 'message': 'All products marked as checked'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
