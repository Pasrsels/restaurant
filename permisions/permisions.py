from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from loguru import logger

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            logger.info(request.user.role)
            if not request.user.role in ['accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return render(request, '403.html', status=403)
            elif request.user.role in ['accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return view_func(request, *args, **kwargs)
            else: return HttpResponseForbidden()
        except Exception as e:
            return redirect('users:login')
    return wrapper

def sales_required(view_func):
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.role in ['sales', 'accountant', 'admin', 'Admin', 'owner', 'Owner']:
                return view_func(request, *args, **kwargs)
            else: return HttpResponseForbidden()
        except Exception as e:
            return redirect('users:login')
    return wrapper