# Agent Instructions - Restaurant Management System

## Commands
- **Test**: `python manage.py test` (all tests), `python manage.py test <app>.<TestClass>.<test_method>` (single test)
- **Run server**: `python manage.py runserver`
- **Check code**: `python manage.py check`
- **Migrations**: `python manage.py makemigrations`, `python manage.py migrate`
- **Shell**: `python manage.py shell` (for interactive testing)

## Architecture
Django 4.2 multi-tenant restaurant POS system with PostgreSQL, Celery, Redis, Django Channels. Apps: `users/` (auth, Company, Branch), `pos/` (sales, receipts), `inventory/` (products, meals, production), `finance/` (expenses, cash book), `analytics/` (reports), `production/` (production planning), `settings/` (config). Multi-tenant: all data filtered by `branch`. Main project: `restaurant/`.

## Code Style
- **Imports**: Django first, third-party, then local. Use `from loguru import logger` for logging.
- **Views**: Use Django class-based views (ListView, DetailView, CreateView) or function-based with decorators. Always filter by `request.user.branch`.
- **Permissions**: Use `@login_required`, `@admin_required`, `@chef_required`, `@sales_required` from `permisions/permisions.py`.
- **Models**: All models must have `branch = ForeignKey(Branch)`. Use Django ORM, never raw SQL.
- **Forms**: Use Django forms with crispy-bootstrap5 styling.
- **Templates**: Located in `templates/<app>/`. Use Django template language.
- **Real-time**: Use Django Channels for WebSocket features (see `pos/consumers.py`, `finance/consumers.py`).
- **Error handling**: Use try-except with logger.error() for debugging.
- **Naming**: snake_case for Python, PascalCase for classes.
- **Never**: Commit secrets, use raw SQL, forget branch filtering, skip migrations.
