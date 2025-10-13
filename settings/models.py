from django.db import models
from users.models import User

class Printer(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, null=True, blank=True)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name 
    
class Module(models.Model):
    """
    Represents modules like Inventory, Finance, POS, etc.
    """
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class EmailNotifications(models.Model):
    NOTIFICATION_TYPES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='notifications', null=True)
    email = models.EmailField(blank=True, null=True)  
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)  
    notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES, default='create')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        target = self.user.email if self.user else self.email
        return f"{target} ({self.notification_type})"
    

