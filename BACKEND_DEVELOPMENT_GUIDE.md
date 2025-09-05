# 🚀 Backend Development Guide - Restaurant Management System

## 📋 Table of Contents
1. [Project Architecture](#project-architecture)
2. [Core Apps & Their Functions](#core-apps--their-functions)
3. [Database Models & Relationships](#database-models--relationships)
4. [API Endpoints & Views](#api-endpoints--views)
5. [Authentication & Permissions](#authentication--permissions)
6. [Business Logic Flow](#business-logic-flow)
7. [File Structure & Key Files](#file-structure--key-files)
8. [Making Changes - Impact Analysis](#making-changes---impact-analysis)
9. [Development Workflow](#development-workflow)

---

## 🏗️ Project Architecture

### **Technology Stack:**
- **Framework**: Django 4.2.19
- **Database**: PostgreSQL (port 5000)
- **Real-time**: Django Channels + WebSockets
- **Task Queue**: Celery + Redis
- **Authentication**: Custom User Model
- **API**: Django REST Framework
- **Permissions**: Custom Permission System

### **Architecture Pattern:**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Django Views  │    │   Database      │
│   (Templates)   │◄──►│   (Controllers) │◄──►│   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Business      │
                       │   Logic Layer   │
                       │   (Models)      │
                       └─────────────────┘
```

---

## 🎯 Core Apps & Their Functions

### **1. `users/` - User Management**
**Purpose**: Handle authentication, user roles, and company/branch management

**Key Files:**
- `models.py` - User, Company, Branch models
- `views.py` - Authentication views
- `forms.py` - User registration/editing forms
- `middleware.py` - Company setup middleware
- `urls.py` - User-related URLs

**Key Models:**
```python
User (Custom User Model)
├── username, email, password
├── role (admin, chef, sales, accountant, owner)
├── company (ForeignKey to Company)
└── branch (ForeignKey to Branch)

Company
├── name, address
└── users (related_name)

Branch
├── company (ForeignKey)
└── branch_name
```

### **2. `inventory/` - Inventory Management**
**Purpose**: Manage products, meals, production, and stock levels

**Key Files:**
- `models.py` - Product, Meal, Dish, Production models
- `views.py` - Inventory management views
- `forms.py` - Product/meal forms
- `context_processors.py` - Notification system
- `tasks.py` - Background tasks

**Key Models:**
```python
Product
├── name, description, price
├── category, supplier
├── stock_level, reorder_point
└── branch (ForeignKey)

Meal
├── name, description, price
├── category, image
├── ingredients (ManyToMany)
└── branch (ForeignKey)

Production
├── production_date, status
├── items (ProductionItems)
└── branch (ForeignKey)
```

### **3. `pos/` - Point of Sale System**
**Purpose**: Handle sales transactions, receipts, and real-time operations

**Key Files:**
- `views.py` - POS operations (1600+ lines!)
- `models.py` - Sale authorization
- `consumers.py` - WebSocket consumers
- `tasks.py` - Background tasks
- `routing.py` - WebSocket routing

**Key Features:**
- Real-time sales processing
- Receipt generation (PDF)
- Payment tracking
- Void/refund handling
- WebSocket notifications

### **4. `finance/` - Financial Management**
**Purpose**: Track sales, expenses, and financial reporting

**Key Files:**
- `models.py` - Sale, Expense, CashBook models
- `views.py` - Financial operations
- `forms.py` - Financial forms
- `consumers.py` - Real-time updates

**Key Models:**
```python
Sale
├── cashier, total_amount, tax
├── sub_total, date, receipt_number
├── staff, change, amount_paid
└── branch (ForeignKey)

Expense
├── category, amount, date
├── user, description
└── branch (ForeignKey)

CashBook
├── sale, expense (ForeignKeys)
├── amount, debit/credit
├── description, date
└── branch (ForeignKey)
```

### **5. `analytics/` - Business Intelligence**
**Purpose**: Generate reports and business analytics

**Key Files:**
- `views.py` - Analytics views
- `models.py` - Analytics models

**Features:**
- Sales analytics by hour/day/month
- Best-selling items tracking
- Performance metrics
- Data visualization

### **6. `settings/` - System Configuration**
**Purpose**: Manage application settings and configuration

**Key Files:**
- `views.py` - Settings management
- `models.py` - Configuration models
- `middleware.py` - Settings middleware

---

## 🔗 Database Models & Relationships

### **Core Relationships:**
```
Company (1) ──► (Many) Branch
Branch (1) ──► (Many) User
Branch (1) ──► (Many) Product
Branch (1) ──► (Many) Sale
Branch (1) ──► (Many) Expense

User (1) ──► (Many) Sale (as cashier)
User (1) ──► (Many) Expense (as user)

Product (Many) ──► (Many) Meal (via ingredients)
Meal (1) ──► (Many) SaleItem
Dish (1) ──► (Many) SaleItem
```

### **Multi-Tenant Architecture:**
- Each **Company** can have multiple **Branches**
- All data is filtered by **Branch** for isolation
- Users belong to specific **Company** and **Branch**

---

## 🌐 API Endpoints & Views

### **URL Structure:**
```
/pos/           - Point of Sale operations
/users/         - User management
/inventory/     - Inventory management
/finance/       - Financial operations
/analytics/     - Business intelligence
/settings/      - System configuration
/admin/         - Django admin panel
```

### **Key View Patterns:**
1. **List Views** - Display collections of objects
2. **Detail Views** - Show individual objects
3. **Create/Update Views** - Form handling
4. **Delete Views** - Object removal
5. **API Views** - JSON responses for AJAX

---

## 🔐 Authentication & Permissions

### **Custom Permission System:**
Located in `permisions/permisions.py`

**Permission Decorators:**
```python
@admin_required      - Only admin users
@sales_required      - Only sales users
@chef_required       - Only chef users
@accountant_required - Only accountant users
@owner_required      - Only owner users
```

### **Middleware:**
- `CompanySetupMiddleware` - Ensures company setup
- `SalesAccessMiddleware` - Controls sales access

---

## 🔄 Business Logic Flow

### **Sales Process:**
```
1. User Login → Authentication
2. POS Interface → Product Selection
3. Sale Creation → Database Transaction
4. Payment Processing → Cash/Change Calculation
5. Receipt Generation → PDF Creation
6. Inventory Update → Stock Reduction
7. Financial Recording → CashBook Entry
8. Real-time Notification → WebSocket Update
```

### **Inventory Management:**
```
1. Product Creation → Database Entry
2. Stock Updates → Real-time Tracking
3. Low Stock Alerts → Notification System
4. Production Planning → Schedule Management
5. End-of-Day Reports → Data Aggregation
```

---

## 📁 File Structure & Key Files

### **Critical Files for Backend Development:**

#### **Configuration Files:**
```
restaurant/
├── settings.py          # Main Django settings
├── urls.py              # Main URL routing
├── asgi.py              # ASGI configuration
├── wsgi.py              # WSGI configuration
└── celery.py            # Celery configuration
```

#### **Model Files (Most Important):**
```
users/models.py          # User, Company, Branch models
inventory/models.py      # Product, Meal, Dish, Production models
finance/models.py        # Sale, Expense, CashBook models
pos/models.py            # POS-specific models
```

#### **View Files (Business Logic):**
```
pos/views.py             # POS operations (1600+ lines)
finance/views.py         # Financial operations (1000+ lines)
inventory/views.py       # Inventory management
users/views.py           # User management
analytics/views.py       # Analytics and reporting
```

#### **Form Files:**
```
users/forms.py           # User registration/editing
finance/forms.py         # Financial forms
inventory/forms.py       # Product/meal forms
```

#### **Permission Files:**
```
permisions/permisions.py # Custom permission decorators
users/middleware.py      # Authentication middleware
middleware/sales_middleware.py # Sales access control
```

#### **Task Files:**
```
pos/tasks.py             # POS background tasks
finance/tasks.py         # Financial background tasks
inventory/tasks.py       # Inventory background tasks
```

#### **WebSocket Files:**
```
pos/consumers.py         # POS real-time updates
finance/consumers.py     # Financial real-time updates
pos/routing.py           # WebSocket routing
```

---

## 🔧 Making Changes - Impact Analysis

### **When You Modify Models:**

#### **1. Adding a New Field to a Model:**
**Files to Update:**
- `models.py` - Add the field
- `forms.py` - Update forms if needed
- `views.py` - Update views to handle new field
- `admin.py` - Add to admin interface
- `templates/` - Update templates to display field
- `migrations/` - Create and run migrations

**Example: Adding `description` to Product model:**
```python
# inventory/models.py
class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)  # NEW FIELD
    price = models.DecimalField(...)
```

**Impact:**
- Create migration: `python manage.py makemigrations`
- Apply migration: `python manage.py migrate`
- Update forms to include description field
- Update views to handle description
- Update templates to display description

#### **2. Adding a New Model:**
**Files to Update:**
- `models.py` - Define the model
- `admin.py` - Register in admin
- `views.py` - Create CRUD views
- `urls.py` - Add URL patterns
- `forms.py` - Create forms
- `templates/` - Create templates

#### **3. Modifying Business Logic:**
**Files to Update:**
- `views.py` - Update view logic
- `models.py` - Update model methods
- `tasks.py` - Update background tasks if needed
- `consumers.py` - Update WebSocket logic if needed

### **When You Modify Views:**

#### **1. Adding a New View:**
**Files to Update:**
- `views.py` - Add the view function/class
- `urls.py` - Add URL pattern
- `templates/` - Create template
- `forms.py` - Add form if needed

#### **2. Modifying Existing View:**
**Files to Update:**
- `views.py` - Update view logic
- `templates/` - Update template if view context changes
- `forms.py` - Update forms if form handling changes

### **When You Modify Permissions:**

#### **1. Adding New Permission:**
**Files to Update:**
- `permisions/permisions.py` - Add new decorator
- `views.py` - Apply decorator to views
- `templates/` - Update template logic

#### **2. Modifying Existing Permissions:**
**Files to Update:**
- `permisions/permisions.py` - Update decorator logic
- `views.py` - Update decorator usage
- `middleware.py` - Update middleware if needed

---

## 🛠️ Development Workflow

### **1. Making Model Changes:**
```bash
# 1. Edit the model
vim inventory/models.py

# 2. Create migration
python manage.py makemigrations

# 3. Apply migration
python manage.py migrate

# 4. Test changes
python manage.py runserver
```

### **2. Making View Changes:**
```bash
# 1. Edit the view
vim inventory/views.py

# 2. Update URL if needed
vim inventory/urls.py

# 3. Update template if needed
vim templates/inventory/your_template.html

# 4. Test changes
python manage.py runserver
```

### **3. Making Permission Changes:**
```bash
# 1. Edit permissions
vim permisions/permisions.py

# 2. Update views to use new permissions
vim your_app/views.py

# 3. Test permissions
python manage.py runserver
```

### **4. Testing Changes:**
```bash
# Run Django checks
python manage.py check

# Run tests (if available)
python manage.py test

# Check for syntax errors
python -m py_compile your_file.py
```

---

## 🎯 Key Development Tips

### **1. Always Check Dependencies:**
When modifying a model, check:
- Forms that use the model
- Views that query the model
- Templates that display model data
- Admin interface
- Serializers (if using DRF)

### **2. Use Django Shell for Testing:**
```bash
python manage.py shell
```
Test your model changes interactively.

### **3. Check Logs:**
The system uses `loguru` for logging. Check logs for errors:
```python
from loguru import logger
logger.info("Your debug message")
```

### **4. Database Queries:**
Use Django's ORM for all database operations:
```python
# Good
Product.objects.filter(branch=request.user.branch)

# Bad
Product.objects.all()  # No branch filtering
```

### **5. Multi-Tenant Awareness:**
Always filter by branch for data isolation:
```python
# In views
queryset = Model.objects.filter(branch=request.user.branch)
```

---

## 🚨 Common Pitfalls

### **1. Forgetting Branch Filtering:**
Always filter data by user's branch for multi-tenant isolation.

### **2. Not Handling Permissions:**
Always add appropriate permission decorators to views.

### **3. Ignoring Migrations:**
Always create and apply migrations when changing models.

### **4. Not Testing Real-time Features:**
Test WebSocket functionality when modifying real-time features.

### **5. Forgetting Context Processors:**
Update context processors when adding global template variables.

---

This guide should help you understand the backend architecture and make informed decisions when modifying the system. Remember to always test your changes thoroughly and consider the impact on other parts of the system.
