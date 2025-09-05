#!/usr/bin/env python
import os
import sys

def run_tests():
    # Set the test settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')
    
    # Import Django after setting the environment variable
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    # Setup Django
    django.setup()
    
    # Get the test runner
    TestRunner = get_runner(settings)
    
    # Run tests
    test_runner = TestRunner(verbosity=2, failfast=False, keepdb=False)
    failures = test_runner.run_tests(['finance.tests'])
    
    # Exit with appropriate status code
    sys.exit(bool(failures))

if __name__ == '__main__':
    run_tests()
