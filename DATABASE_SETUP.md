# Database Setup Guide

## Connecting to Local PostgreSQL

This guide will help you connect your Restaurant Management System to your local PostgreSQL database.

### Prerequisites

1. **PostgreSQL installed and running** on your local machine
2. **Python dependencies installed** (run `pip install -r requirements.txt`)

### Step 1: Verify PostgreSQL Installation

First, make sure PostgreSQL is running on your system:

**Windows:**
```bash
# Check if PostgreSQL service is running
sc query postgresql

# Or start it if not running
net start postgresql
```

**Alternative check:**
```bash
# Try connecting with psql
psql -U postgres -h localhost
```

### Step 2: Configure Database Connection

The project is now configured to use environment variables. You can set them in several ways:

#### Option A: Create a .env file (Recommended)
Create a `.env` file in the project root with:
```
DB_NAME=restaurant
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

#### Option B: Set environment variables directly
```bash
# Windows PowerShell
$env:DB_NAME="restaurant"
$env:DB_USER="postgres"
$env:DB_PASSWORD="your_postgres_password"
$env:DB_HOST="localhost"
$env:DB_PORT="5432"

# Windows Command Prompt
set DB_NAME=restaurant
set DB_USER=postgres
set DB_PASSWORD=your_postgres_password
set DB_HOST=localhost
set DB_PORT=5432
```

### Step 3: Run Database Setup

Run the database setup script:
```bash
python setup_database.py
```

This script will:
- Connect to your PostgreSQL server
- Create the `restaurant` database if it doesn't exist
- Test the connection

### Step 4: Run Django Migrations

After successful database setup:
```bash
# Create database migrations
python manage.py makemigrations

# Apply migrations to create tables
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Run the development server
python manage.py runserver
```

### Troubleshooting

#### Common Issues:

1. **Connection refused**
   - Make sure PostgreSQL is running
   - Check if the port (5432) is correct
   - Verify firewall settings

2. **Authentication failed**
   - Check your PostgreSQL password
   - Verify the username (default: postgres)
   - Make sure the user has proper permissions

3. **Database doesn't exist**
   - The setup script will create it automatically
   - Or create manually: `CREATE DATABASE restaurant;`

4. **Permission denied**
   - Make sure your PostgreSQL user has CREATE DATABASE privileges
   - Run as PostgreSQL superuser if needed

#### PostgreSQL Commands for Manual Setup:

```sql
-- Connect to PostgreSQL
psql -U postgres

-- Create database
CREATE DATABASE restaurant;

-- Create user (if needed)
CREATE USER restaurant_user WITH PASSWORD 'your_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE restaurant TO restaurant_user;

-- Exit
\q
```

### Default Configuration

If you don't set environment variables, the system will use these defaults:
- **Database Name**: `restaurant`
- **Username**: `postgres`
- **Password**: `neverfail`
- **Host**: `localhost`
- **Port**: `5432`

### Verification

To verify everything is working:
1. Run the setup script: `python setup_database.py`
2. Check Django can connect: `python manage.py check`
3. Run migrations: `python manage.py migrate`
4. Start the server: `python manage.py runserver`

If all steps complete without errors, your database connection is working correctly!

