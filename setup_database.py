#!/usr/bin/env python
"""
Database setup script for Restaurant Management System
This script helps you configure and set up your PostgreSQL database.
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def create_database():
    """Create the database if it doesn't exist"""
    try:
        # Get database configuration
        db_name = os.getenv('DB_NAME', 'restaurant')
        db_user = os.getenv('DB_USER', 'postgres')
        db_password = os.getenv('DB_PASSWORD', 'ms123456789')
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5000')
        
        print(f"Attempting to connect to PostgreSQL at {db_host}:{db_port}")
        print(f"Database: {db_name}")
        print(f"User: {db_user}")
        
        # Connect to PostgreSQL server (not to a specific database)
        conn = psycopg2.connect(
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
            database='postgres'  # Connect to default postgres database
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Creating database '{db_name}'...")
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Database '{db_name}' created successfully!")
        else:
            print(f"Database '{db_name}' already exists.")
        
        cursor.close()
        conn.close()
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"Error connecting to PostgreSQL: {e}")
        print("\nPlease make sure:")
        print("1. PostgreSQL is installed and running")
        print("2. The credentials are correct")
        print("3. PostgreSQL is accessible on the specified host and port")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

def test_connection():
    """Test the database connection"""
    try:
        db_name = os.getenv('DB_NAME', 'restaurant')
        db_user = os.getenv('DB_USER', 'postgres')
        db_password = os.getenv('DB_PASSWORD', 'ms123456789')
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5000')
        
        conn = psycopg2.connect(
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        
        cursor = conn.cursor()
        cursor.execute('SELECT version();')
        version = cursor.fetchone()
        
        print(f"Successfully connected to PostgreSQL!")
        print(f"PostgreSQL version: {version[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error testing connection: {e}")
        return False

def main():
    print("=== Restaurant Management System Database Setup ===")
    print()
    
    # Create database
    if create_database():
        print()
        # Test connection
        if test_connection():
            print()
            print("✅ Database setup completed successfully!")
            print()
            print("Next steps:")
            print("1. Run: python manage.py makemigrations")
            print("2. Run: python manage.py migrate")
            print("3. Run: python manage.py createsuperuser")
            print("4. Run: python manage.py runserver")
        else:
            print("❌ Database connection test failed!")
    else:
        print("❌ Database setup failed!")

if __name__ == "__main__":
    main()
