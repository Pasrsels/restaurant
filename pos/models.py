from django.db import models

class SaleAuthorization(models.Model):
    auth_date = models.DateField(auto_now_add=True)
    auth_granted = models.BooleanField(default=False)
    
class SalesAmountTracker(models.Model):
    cashier = models.ForeignKey('users.User', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0) 
    date =  models.DateTimeField(auto_now_add=True)
    time_tracker = models.TimeField(auto_now_add=True)
    
    def __str__(self):
        return self.amount