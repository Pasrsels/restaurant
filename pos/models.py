from django.db import models

class Authorization(models.Model):
    auth_date = models.DateField(auto_now_add=True)
    auth_granted = models.BooleanField(default=False)