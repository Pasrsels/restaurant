from django.urls import path
from . import views

app_name = "settings"

urlpatterns = [
    path("", views.settings, name="settings"),
    path("notifications/", views.list_emails, name="list_emails"),
    path("notifications/add-email/", views.add_email_notification, name="add_email_notification"),
    path("notifications/remove-email/<int:email_id>/", views.remove_email_notification, name="remove_email_notification"),
    path("modules/add/", views.add_module, name="add_module"),  # <-- New
]
