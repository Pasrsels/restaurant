from django import forms
from loguru import logger
from users.models import User, Company, Branch
from django.contrib.auth.forms import UserCreationForm

class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'username',
            'email',
            'phonenumber',
            'company',
            'role',
            'password',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter companies
        if 'company' in self.fields:
            self.fields['company'].queryset = Company.objects.all()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserDetailsForm(forms.ModelForm):

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'username',
            'email',
            'phonenumber',
            'role',
            'company',
            'branch'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'branch' in self.fields:
            self.fields['branch'].queryset = Branch.objects.all()

class UserDetailsForm2(forms.ModelForm):
   
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'username',
            'email',
            'phonenumber',
            'role',
            'branch'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'branch' in self.fields:
            self.fields['branch'].queryset = Branch.objects.all()


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'address']

class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['branch_name']

class CustomUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField(max_length=254)
    phonenumber = forms.CharField(max_length=13)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phonenumber', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user
