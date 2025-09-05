import psycopg2
from django.conf import settings

def check_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=settings.DATABASES['default']['NAME'],
            user=settings.DATABASES['default']['USER'],
            password=settings.DATABASES['default']['PASSWORD'],
            host=settings.DATABASES['default']['HOST'],
            port=settings.DATABASES['default']['PORT']
        )
        print("✅ Database connection successful!")
        print(f"Database: {settings.DATABASES['default']['NAME']}")
        print(f"User: {settings.DATABASES['default']['USER']}")
        print(f"Host: {settings.DATABASES['default']['HOST']}")
        print(f"Port: {settings.DATABASES['default']['PORT']}")
        conn.close()
    except Exception as e:
        print("❌ Database connection failed!")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurant.settings')
    django.setup()
    check_db_connection()
