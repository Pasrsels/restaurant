from django.http import HttpResponseForbidden
from django.shortcuts import render

def admin_required(view_func):
    # def wrapper(request, *args, **kwargs):
    #     if request.user:
    #         if request.user.role in ['accountant', 'admin', 'Admin', 'owner', 'Owner']:
    #             return view_func(request, *args, **kwargs)
    #         else: return HttpResponseForbidden()
    # return wrapper
    pass

def sales_required(view_func):
    # def wrapper(request, *args, **kwargs):
    #     if request.user:
    #         if request.user.role in ['sales', 'accountant', 'admin', 'Admin', 'owner', 'Owner']:
    #             return view_func(request, *args, **kwargs)
    #         else: return HttpResponseForbidden()
    # return wrapper
    pass