#!/usr/bin/env python3
"""
Script to create and apply migrations for DocumentFile model changes

This script:
1. Creates migrations for the DocumentFile model changes
2. Applies the migrations to update the database schema
3. Shows the status of migrations
"""

import os
import sys
import django
import subprocess

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parliament_api.settings')
django.setup()

def run_command(command, description):
    """Run a management command and return success status"""
    print(f"\n🔧 {description}")
    print(f"   Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(f"✅ Success!")
        if result.stdout:
            print(f"   Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed!")
        print(f"   Error: {e}")
        if e.stdout:
            print(f"   Output: {e.stdout}")
        if e.stderr:
            print(f"   Error Output: {e.stderr}")
        return False

def main():
    print("🏛️ Parliament API - Database Migration Script")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not os.path.exists('manage.py'):
        print("❌ manage.py not found. Please run this script from the parliament_api directory.")
        return 1
    
    # Step 1: Create migrations for files app
    print("\n📋 Step 1: Creating migrations for DocumentFile model changes")
    success = run_command(
        ['python', 'manage.py', 'makemigrations', 'files', '--name', 'add_document_categories'],
        "Creating migration for document categories"
    )
    
    if not success:
        print("❌ Failed to create migrations. Please check the model changes.")
        return 1
    
    # Step 2: Show migration status
    print("\n📋 Step 2: Checking migration status")
    run_command(
        ['python', 'manage.py', 'showmigrations', 'files'],
        "Showing files app migration status"
    )
    
    # Step 3: Apply migrations
    print("\n📋 Step 3: Applying migrations")
    user_input = input("\nDo you want to apply the migrations now? (y/N): ")
    
    if user_input.lower() == 'y':
        success = run_command(
            ['python', 'manage.py', 'migrate'],
            "Applying all pending migrations"
        )
        
        if success:
            print("\n✅ All migrations applied successfully!")
            print("   The DocumentFile model now supports document categories.")
        else:
            print("\n❌ Migration failed. Please check the errors above.")
            return 1
    else:
        print("\n⏭️  Skipping migration. Run 'python manage.py migrate' when ready.")
    
    # Step 4: Final status check
    print("\n📋 Step 4: Final migration status")
    run_command(
        ['python', 'manage.py', 'showmigrations'],
        "Showing all app migration status"
    )
    
    print(f"\n✅ Migration script completed!")
    print(f"📝 Summary of changes:")
    print(f"   - Added 'document_category' field to DocumentFile model")
    print(f"   - Made 'question' field nullable to support debates")
    print(f"   - Updated indexes for better performance")
    print(f"   - Enhanced __str__ method for better representation")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

