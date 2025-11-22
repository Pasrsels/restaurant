from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from loguru import logger
from utils.authenticate import authenticate_user
from .models import User 
from .forms import UserRegistrationForm, UserDetailsForm, UserDetailsForm2, BranchForm
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import make_password
from .models import Company, User, Branch
from .forms import CompanyForm, CustomUserCreationForm
from settings.models import Module
from django.db import transaction
from permisions.permisions import admin_required
import json
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

def create_company(request):
    if Company.objects.exists():
        return redirect('users:login')

    if request.method == 'POST':
        company_form = CompanyForm(request.POST)
        user_form = CustomUserCreationForm(request.POST)
        branch_form = BranchForm(request.POST)
        
        if company_form.is_valid() and user_form.is_valid() and branch_form.is_valid():
            logger.info(request.POST)
            with transaction.atomic():
                company = company_form.save()

                branch = branch_form.save(commit=False)
                branch.company = company
                branch.save()
                
                user = user_form.save(commit=False)
                user.company = company
                user.branch = branch
                user.role = 'owner'
                user.save()
       
                modules = ['Sales', 'Finance', 'Inventory', 'Production']
                bulk_modules = []

                for m in modules:
                    bulk_modules.append(Module(name=m))

                Module.objects.bulk_create(bulk_modules)
            return redirect('users:login')
        else:
            messages.warning(request, f'Company registration form not valid.')
    else:
        company_form = CompanyForm()
        user_form = CustomUserCreationForm()
        branch_form = BranchForm()

    return render(request, 'create_company.html', {'company_form': company_form, 'user_form': user_form, 'branch_form':branch_form})


def users(request):
    search_query = request.GET.get('q', '')
    role = request.GET.get('role', '')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 25))

    qs = User.objects.filter(branch=request.user.branch)
    if search_query:
        qs = qs.filter(Q(username__icontains=search_query) | Q(email__icontains=search_query) | Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query))
    if role:
        qs = qs.filter(role=role)
    if start_date and end_date:
        try:
            from datetime import datetime as _dt
            start_dt = _dt.strptime(start_date, '%Y-%m-%d')
            end_dt = _dt.strptime(end_date, '%Y-%m-%d')
            qs = qs.filter(date_joined__date__gte=start_dt.date(), date_joined__date__lte=end_dt.date())
        except Exception:
            pass

    qs = qs.order_by('first_name', 'last_name')

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    form = UserRegistrationForm()
    user_details_form = UserDetailsForm2()
    branch_form = BranchForm()

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.password = make_password(form.cleaned_data['password'])
            if not user.branch:
                user.branch = request.user.branch
            user.save()
            messages.success(request, 'User successfully added')
        else:
            messages.warning(request, 'Invalid form data')

    return render(request, 'auth/users.html', {
        'users': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'form': form,
        'user_details_form': user_details_form,
        'branch': branch_form,
        'filter_role': role,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
        'page_size': page_size,

        'branches': Branch.objects.all(),
    })

# added delete function /view
# @admin_required
@require_POST
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    messages.success(request, 'User deleted successfully.')
    return JsonResponse({'success': True, 'message': 'User deleted successfully'})
# end of new update here

def login_view(request):
    if request.method == 'POST':
        logger.info('here')
        email_address = request.POST['email_address']
        password = request.POST['password']

        # Validate email
        try:
            validate_email(email_address)
        except ValidationError:
            messages.error(request, 'Invalid email format')
            return render(request, 'auth/login.html')

        user = authenticate_user(email=email_address, password=password)
        logger.info(f'User: {user}')
        if user is not None:
            if user.is_active:
                login(request, user)
                logger.info(f'User: {user.first_name + " " + user.email} logged in')
                logger.info(f'User role: {user.role}')

                # session_key = request.session.session_key
                # user.session_key = session_key
                # user.save()

                # logger.info(f'logged with session key: {session_key}')
                if user.role in ['accountant', 'admin', 'owner']:
                    logger.info(f'User: {user.first_name + " " + user.email} is an {user.role}')
                    return redirect('/')
                elif user.role in ['chef', 'stores_person']:
                    logger.info(f'User: {user.first_name + " " + user.email} is a {user.role}')
                    return redirect('inventory:production_plans')
                return redirect('pos:pos')
            else:
                messages.error(request, 'Your account is not active, contact admin')
        else:
            messages.warning(request, 'Invalid username or password')

    return render(request, 'auth/login.html')


def user_edit(request, user_id):
    user = User.objects.get(id=user_id)
    
    logger.info(f'User details: {user.first_name + " " + user.email}')
    
    if request.method == 'POST':
        form = UserDetailsForm2(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'User details updated successfully')
            logger.success(f'User successfully edited: {user.first_name} by {request.user}')
        else:
            messages.error(request, 'Invalid form data')
    else:
        form = UserDetailsForm2(instance=user)
    return render(request, 'auth/users.html', {'user': user, 'form': form})


def user_detail(request, user_id):
    user = User.objects.get(id=user_id)
    form = UserDetailsForm()

    logger.info(f'User details: {user.first_name + " " + user.email}')
    # render user details
    if request.method == 'GET':
        return render(request, 'users/user_detail.html', {'user': user, 'form': form})
    if request.method == 'POST':
        form = UserDetailsForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'User details updated successfully')
        else:
            messages.error(request, 'Invalid form data')
        return render(request, 'users/user_detail.html', {'user': user, 'form': form})


def register(request):
    form = UserRegistrationForm()
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            user = form.save(commit=False)
            user.password = make_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, 'User successfully added')
        else:
            messages.error(request, 'Error')
    return render(request, 'auth/register.html', {
        'form': form
    })



def get_user_data(request, user_id):
    user = User.objects.get(id=user_id)
    user_data = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'username': user.username,
        'phonenumber': user.phonenumber,
        'role': user.role,
        'company': user.company.id if user.company else None,
    }
    logger.info(f'User data: {user_data}')
    return JsonResponse(user_data)


def logout_view(request):
    logout(request)
    return redirect('users:login')


def createBranch(request):
    if request.method == 'GET':
        branch_info = Branch.objects.all()
        branch_form = BranchForm()
        return #return html page with data context
    elif request.method == 'POST':
        branch_form = BranchForm(request.POST)
        company_info = Company.objects.all().first()

        if branch_form.is_valid():
            branch = branch_form.save(commit=False)
            branch.company = company_info
            branch.save()

            messages.success(request, f'Successfully saved {branch.name}')
            return redirect('users:create_branch') 
        
        messages.warning(request, f'Failed to save')
        return redirect('users:create_branch')
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            branch_id = data.get('id') 
            if not branch_id:
                messages.warning(request, 'No branch ID provided')
                return redirect('users:create_branch')

            branch_instance = get_object_or_404(Branch, id=branch_id)
            branch_form = BranchForm(data, instance=branch_instance)

            if branch_form.is_valid():
                branch = branch_form.save(commit=False)
                branch.company = Company.objects.first()
                branch.save()

                messages.success(request, f'Successfully updated {branch.name}')
                return redirect('users:create_branch')
            else:
                messages.warning(request, 'Invalid form data')
                return redirect('users:create_branch')
        except json.JSONDecodeError:
            messages.error(request, 'Invalid JSON')
            return redirect('users:create_branch')

    elif request.method == 'DELETE':
        try:
            body = json.loads(request.body)
            name = body.get('name')
            if name:
                branch_info = Branch.objects.get(name=name)
                branch_info.delete()
                messages.success(request, f'Successfully deleted branch: {name}')
            else:
                messages.warning(request, 'No branch name provided')
        except Branch.DoesNotExist:
            messages.error(request, 'Branch not found')
        except json.JSONDecodeError:
            messages.error(request, 'Invalid JSON')
        return redirect('users:create_branch')

@admin_required
def getBranches(request):
    if request.method == 'GET':
        branch = Branch.objects.all()
        branch_list = []
        for info in branch:
            branch_list.append(
                {
                    'id': info.id,
                    'name': info.branch_name
                }
            )
        logger.info(branch_list)
        return JsonResponse({'success':True, 'branch': branch_list}, status=200)
    elif request.method == 'POST':
        data = json.loads(request.body)
        logger.info(data)
        user = request.user
        if data:
            branch_info = Branch.objects.get(id = data)
            user.branch = branch_info
            user.save()
            return JsonResponse({'success': True}, status = 200)
        return JsonResponse({'success': False}, status = 400)

# @admin_required
def createBranch(request):
    if request.method == 'GET':
        branchs_data = Branch.objects.all()
        data_list = [b.branch_name for b in branchs_data if b]
        logger.info(data_list)
        return JsonResponse({'success': True, 'branch': data_list}, status = 200)
    if request.method == 'POST':
        # branch_form = BranchForm(request.POST)
        logger.info(request.POST.get('branch_name'))
        company_info = Company.objects.all().first()
        logger.info({
            'Company':company_info,
            'Request': request.POST
        })
        if request.POST.get('branch_name'):
            logger.info(request.POST.get('branch_name'))
            b = Branch.objects.create(
                company = company_info,
                branch_name = request.POST.get('branch_name')
            )
            logger.info(b)
            messages.success(request, f'Successfully saved new branch')
            return redirect('users:users')
        messages.warning(request, f'Failed to save new branch')
        return redirect('users:users')

@admin_required
def load_branches(request):
    """AJAX view to load branches based on selected company"""
    company_id = request.GET.get('company')
    if company_id:
        branches = Branch.objects.filter(company_id=company_id).order_by('branch_name')
        return JsonResponse({
            'success': True,
            'branches': [{'id': branch.id, 'name': branch.branch_name} for branch in branches]
        })
    return JsonResponse({'success': False, 'branches': []})
