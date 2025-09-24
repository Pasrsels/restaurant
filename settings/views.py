from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import EmailNotifications, Module, User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

@login_required
def settings(request):
    return render(request, 'settings/settings.html')

@login_required
def list_emails(request):
    context = {
        'modules': Module.objects.all(),
        'system_users': User.objects.all(),
        'notifications': EmailNotifications.objects.select_related('module', 'user')
    }
    return render(request, 'settings/notifications/list.html', context)
    
@require_POST
def add_email_notification(request):
    module_id = request.POST.get("module_id")
    email = request.POST.get("email")
    user_id = request.POST.get("user")

    module = get_object_or_404(Module, id=module_id)

    if not email and not user_id:
        messages.error(request, "Please provide an email or select a user.")
        return redirect("settings:email_list")

    if user_id:
        user = get_object_or_404(User, id=user_id)
        email = user.email
    else:
        user = None

    existing_notification = EmailNotifications.objects.filter(
        module=module,
        email=email
    ).first()
    if existing_notification:
        messages.warning(request, "This email is already registered for this module.")
        return redirect("settings:email_list")

    EmailNotifications.objects.create(
        module=module,
        email=email,
        user=user,
        notification_type=request.POST.get("notification_type", "create"),
        is_active=True,
    )

    messages.success(request, "Email notification added successfully!")
    return redirect("settings:email_list")


@require_POST
def remove_email_notification(request, email_id):
    try:
        notification = get_object_or_404(EmailNotifications, id=email_id)
        notification.delete()
        return JsonResponse({'status': 'success'}, status=200)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

from django.views.decorators.http import require_http_methods

@login_required
@require_http_methods(["GET", "POST"])
def add_module(request):
    if request.method == "POST":
        name = request.POST.get("name")

        if not name:
            messages.error(request, "Module name cannot be empty.")
            return redirect("settings:add_module")

        if Module.objects.filter(name__iexact=name).exists():
            messages.warning(request, "This module already exists.")
            return redirect("settings:add_module")

        Module.objects.create(name=name)
        messages.success(request, f"Module '{name}' added successfully!")
        return redirect("settings:email_list")

    return render(request, "settings/modules/add_module.html")
