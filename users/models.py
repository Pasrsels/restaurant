from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

class CustomUserManager(BaseUserManager):
    """
    Custom user model manager with extra functionalities.
    """

    def create_user(self, email, password, **extra_fields):
        """
        Creates and saves a User with the given email, password and extra fields.
        If the first user created, grant them superuser and (optionally) admin group access.
        """
        if not email:
            raise ValueError('The Email field is required')
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.is_staff = True
        user.save(using=self._db)

        if self.model.objects.count() == 1:
            user.is_superuser = True
            user.company = Company.objects.get(id=1)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Creates and saves a SuperUser with the given email, password and extra fields.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is False:
            raise ValueError('Superuser must have is_staff=True.')

        if extra_fields.get('is_superuser') is False:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class Company(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
     
    def __str__(self) -> str:
        return self.name

class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)
    branch_name = models.CharField(max_length=60, null=True)
    # name = models.CharField(max_length=60, null=True)

    def __str__(self):
        return self.branch_name

class User(AbstractUser):
    
    USER_ROLES = (
        ('admin', 'Admin'),
        ('chef', 'Chef'),
        ('sales', 'Salesperson'),
        ('accountant', 'Accountant'),
        ('owner', 'Owner'), 
        ('stores_person', 'Stores Person'),
        ('supervisor', 'supervisor')
    )
    
    phonenumber = models.CharField(max_length=13)
    role = models.CharField(choices=USER_ROLES, max_length=50)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="users", null=True)
    branch = models.ForeignKey('Branch', on_delete=models.CASCADE, null=True, blank=True)
    # image = models.ImageField(upload_to='profile', null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.first_name} {self.last_name}'
