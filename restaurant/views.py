from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from permisions.permisions import admin_required


@login_required
def Dashboard(request):
    return render(request, 'dashboard.html')