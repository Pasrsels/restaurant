from django.core.management.base import BaseCommand
from django.contrib.auth import authenticate
from users.models import User, Company, Branch
from inventory.models import Production
import os

class Command(BaseCommand):
    help = 'Find admin user with username "admin" and password "never fail" and check their permissions'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Searching for admin user...'))
        
        # First, let's check if the user exists with username "admin"
        try:
            admin_user = User.objects.get(username='admin')
            self.stdout.write(self.style.SUCCESS(f'✅ Found user with username "admin"'))
            self.stdout.write(f'   - ID: {admin_user.id}')
            self.stdout.write(f'   - Email: {admin_user.email}')
            self.stdout.write(f'   - First Name: {admin_user.first_name}')
            self.stdout.write(f'   - Last Name: {admin_user.last_name}')
            self.stdout.write(f'   - Role: {admin_user.role}')
            self.stdout.write(f'   - Is Staff: {admin_user.is_staff}')
            self.stdout.write(f'   - Is Superuser: {admin_user.is_superuser}')
            self.stdout.write(f'   - Is Active: {admin_user.is_active}')
            self.stdout.write(f'   - Date Joined: {admin_user.date_joined}')
            
            if admin_user.company:
                self.stdout.write(f'   - Company: {admin_user.company.name}')
            else:
                self.stdout.write(f'   - Company: None')
                
            if admin_user.branch:
                self.stdout.write(f'   - Branch: {admin_user.branch.branch_name}')
            else:
                self.stdout.write(f'   - Branch: None')
            
            # Now let's test the password "never fail"
            self.stdout.write('\n🔐 Testing password authentication...')
            authenticated_user = authenticate(username='admin', password='never fail')
            
            if authenticated_user:
                self.stdout.write(self.style.SUCCESS('✅ Password "never fail" is correct!'))
                self.stdout.write(f'   - Authenticated user: {authenticated_user.username}')
            else:
                self.stdout.write(self.style.WARNING('❌ Password "never fail" is incorrect'))
                self.stdout.write('   - Authentication failed')
            
            # Check production plan access
            self.stdout.write('\n📋 Checking production plan access...')
            if admin_user.role in ['admin', 'owner', 'accountant']:
                self.stdout.write(self.style.SUCCESS(f'✅ User has admin role ({admin_user.role}) - can access all production plans'))
                total_plans = Production.objects.all().count()
                self.stdout.write(f'   - Total production plans in system: {total_plans}')
                
                # Show some recent production plans
                recent_plans = Production.objects.all().order_by('-date_created')[:5]
                if recent_plans:
                    self.stdout.write(f'   - Recent production plans:')
                    for plan in recent_plans:
                        self.stdout.write(f'     * {plan.id}: {plan.dish.name if plan.dish else "No dish"} - {plan.date_created}')
                else:
                    self.stdout.write(f'   - No production plans found')
                    
            elif admin_user.branch:
                self.stdout.write(self.style.WARNING(f'⚠️ User has role {admin_user.role} - can only access plans from branch: {admin_user.branch.branch_name}'))
                branch_plans = Production.objects.filter(branch=admin_user.branch).count()
                self.stdout.write(f'   - Production plans in user\'s branch: {branch_plans}')
            else:
                self.stdout.write(self.style.ERROR(f'❌ User has role {admin_user.role} but no branch assigned - limited access'))
            
            # Check POS access
            self.stdout.write('\n🛒 Checking POS access...')
            if admin_user.role in ['admin', 'owner', 'accountant', 'sales']:
                self.stdout.write(self.style.SUCCESS(f'✅ User can access POS (role: {admin_user.role})'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠️ User may have limited POS access (role: {admin_user.role})'))
                
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ No user found with username "admin"'))
            
            # Let's show all users in the system
            self.stdout.write('\n👥 All users in the system:')
            all_users = User.objects.all()
            if all_users:
                for user in all_users:
                    self.stdout.write(f'   - {user.username} (Role: {user.role}, Company: {user.company.name if user.company else "None"})')
            else:
                self.stdout.write('   - No users found in the system')
        
        # Show database connection info
        self.stdout.write('\n🗄️ Database connection info:')
        self.stdout.write(f'   - DB_NAME: {os.getenv("DB_NAME", "restaurant")}')
        self.stdout.write(f'   - DB_USER: {os.getenv("DB_USER", "postgres")}')
        self.stdout.write(f'   - DB_HOST: {os.getenv("DB_HOST", "localhost")}')
        self.stdout.write(f'   - DB_PORT: {os.getenv("DB_PORT", "5000")}')
        
        # Show companies and branches
        self.stdout.write('\n🏢 Companies and Branches:')
        companies = Company.objects.all()
        if companies:
            for company in companies:
                self.stdout.write(f'   - Company: {company.name}')
                branches = Branch.objects.filter(company=company)
                if branches:
                    for branch in branches:
                        self.stdout.write(f'     * Branch: {branch.branch_name}')
                else:
                    self.stdout.write(f'     * No branches')
        else:
            self.stdout.write('   - No companies found')
