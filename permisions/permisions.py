from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from loguru import logger

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            logger.info(request.user.role)
            if not request.user.role in ['accountant', 'admin', 'Admin', 'owner', 'Owner', 'chef', 'stores_person']:
                return render(request, '403.html', status=403)
            elif request.user.role in ['accountant', 'admin', 'Admin', 'owner', 'Owner', 'chef', 'stores_person']:
                return view_func(request, *args, **kwargs)
            else: return HttpResponseForbidden()
        except Exception as e:
            return redirect('users:login')
    return wrapper

def can_declare_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            print(request.user.role, 'user role')
            if request.user.role in ['chef', 'admin', 'Admin', 'owner', 'Owner', 'sales']:
                return view_func(request, *args, **kwargs)
            else:
                return render(request, '403.html', status=403)
        except Exception as e:
            return redirect('users:login')
    return wrapper

def can_confirm_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['stores_person', 'accountant', 'admin', 'Admin', 'owner', 'Owner', 'sales']:
                return view_func(request, *args, **kwargs)
            else:
                return render(request, '403.html', status=403)
        except Exception as e:
            return redirect('users:login')
    return wrapper

def sales_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['sales', 'accountant', 'admin', 'Admin', 'owner', 'Owner', 'chef', 'stores_person']:
                return view_func(request, *args, **kwargs)
            else: return HttpResponseForbidden()
        except Exception as e:
            return redirect('users:login')
    return wrapper

def chef_or_stores_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['chef', 'stores_person', 'accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return view_func(request, *args, **kwargs)
            else: return HttpResponseForbidden()
        except Exception as e:
            return redirect('users:login')
    return wrapper

def chef_only_required(view_func):
    """Only chef can access - stores person cannot"""
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['chef', 'accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return view_func(request, *args, **kwargs)
            else: 
                return render(request, '403.html', status=403)
        except Exception as e:
            return redirect('users:login')
    return wrapper

def stores_person_only_required(view_func):
    """Only stores person can access - chef cannot"""
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['stores_person', 'accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return view_func(request, *args, **kwargs)
            else: 
                return render(request, '403.html', status=403)
        except Exception as e:
            return redirect('users:login')
    return wrapper

def chef_or_stores_view_required(view_func):
    """Both chef and stores person can view, but actions are restricted based on role"""
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['chef', 'stores_person', 'accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return view_func(request, *args, **kwargs)
            else: 
                return render(request, '403.html', status=403)
        except Exception as e:
            print('error', e)
            return redirect('users:login')
    return wrapper
