from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Company, Branch

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'email', 'role', 'company', 'branch', 'is_active']
    list_filter = ['role', 'company', 'branch', 'is_active', 'is_staff']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering = ['username']
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phonenumber')}),
        ('Organization', {'fields': ('company', 'branch', 'role')}),
        ('Permissions', {
            
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email', 'phonenumber', 'company', 'branch', 'role'),
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "company":
            kwargs["queryset"] = Company.objects.all().order_by('name')
        elif db_field.name == "branch":
            kwargs["queryset"] = Branch.objects.all().order_by('branch_name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Media:
        js = ('js/user_admin.js',)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'address']
    search_fields = ['name']

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['branch_name', 'company']
    list_filter = ['company']
    search_fields = ['branch_name', 'company__name']
