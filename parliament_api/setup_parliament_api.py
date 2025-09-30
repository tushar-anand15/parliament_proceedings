#!/usr/bin/env python
"""
Parliament API Setup Script

This script sets up the Parliament API with:
1. Database migrations
2. Admin user creation
3. GCS bucket initialization
4. Authentication setup
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parliament_api.settings')
django.setup()

from django.core.management import execute_from_command_line
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.conf import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migrations():
    """Run database migrations"""
    logger.info("Running database migrations...")
    try:
        execute_from_command_line(['manage.py', 'migrate'])
        logger.info("✅ Database migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


def create_admin_user():
    """Create admin user and return credentials"""
    logger.info("Setting up admin user...")
    
    username = settings.ADMIN_USERNAME
    password = settings.ADMIN_PASSWORD
    email = settings.ADMIN_EMAIL
    
    try:
        # Create or update admin user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'is_staff': True,
                'is_superuser': True,
                'is_active': True
            }
        )

        if created:
            user.set_password(password)
            user.save()
            logger.info(f"✅ Created new admin user: {username}")
        else:
            # Update password and permissions
            user.set_password(password)
            user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            logger.info(f"✅ Updated existing admin user: {username}")

        # Create or get auth token
        token, token_created = Token.objects.get_or_create(user=user)
        
        if token_created:
            logger.info("✅ Created new auth token")
        else:
            logger.info("✅ Using existing auth token")

        return {
            'username': username,
            'password': password,
            'email': email,
            'token': token.key,
            'created': created
        }
    
    except Exception as e:
        logger.error(f"❌ Failed to create admin user: {e}")
        return None


def setup_gcs_buckets():
    """Initialize GCS buckets"""
    logger.info("Setting up Google Cloud Storage buckets...")
    
    try:
        from services.cloud_storage.gcs_service import GCSService
        
        gcs_service = GCSService()
        
        # Test connection and create buckets
        debates_bucket = gcs_service._get_bucket(settings.GCS_DEBATES_BUCKET)
        questions_bucket = gcs_service._get_bucket(settings.GCS_QUESTIONS_BUCKET)
        
        logger.info(f"✅ GCS buckets ready:")
        logger.info(f"   - Debates: {settings.GCS_DEBATES_BUCKET}")
        logger.info(f"   - Questions: {settings.GCS_QUESTIONS_BUCKET}")
        logger.info(f"   - Region: {settings.GCS_REGION}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ GCS setup failed: {e}")
        logger.error("Please check your GCS credentials and permissions")
        return False


def display_setup_summary(admin_credentials):
    """Display setup summary"""
    print("\n" + "="*60)
    print("🎉 PARLIAMENT API SETUP COMPLETE")
    print("="*60)
    
    if admin_credentials:
        print("\n📋 ADMIN CREDENTIALS:")
        print(f"   Username: {admin_credentials['username']}")
        print(f"   Password: {admin_credentials['password']}")
        print(f"   Email: {admin_credentials['email']}")
        print(f"   Auth Token: {admin_credentials['token']}")
    
    print("\n🔧 CONFIGURATION:")
    print(f"   GCS Project: {settings.GCS_PROJECT_ID}")
    print(f"   Debates Bucket: {settings.GCS_DEBATES_BUCKET}")
    print(f"   Questions Bucket: {settings.GCS_QUESTIONS_BUCKET}")
    print(f"   Region: {settings.GCS_REGION}")
    
    print("\n🚀 API ENDPOINTS:")
    print("   Admin: http://localhost:8000/admin/")
    print("   API Docs: http://localhost:8000/api/schema/swagger-ui/")
    print("   API Root: http://localhost:8000/api/")
    
    print("\n📝 AUTHENTICATION:")
    print("   All API endpoints now require authentication")
    print("   Use Token Authentication with the token above")
    print("   Header: Authorization: Token <your_token>")
    
    print("\n⚠️  IMPORTANT NOTES:")
    print("   - Save the admin credentials securely")
    print("   - GCS credentials are stored in: parliament-process-90c920ce4243.json")
    print("   - Local files will be auto-deleted after GCS upload (configurable)")
    print("   - Presigned URLs expire after 1 hour by default")
    
    print("\n" + "="*60)


def main():
    """Main setup function"""
    print("🔧 Starting Parliament API Setup...")
    
    success_count = 0
    total_steps = 3
    
    # Step 1: Run migrations
    if run_migrations():
        success_count += 1
    
    # Step 2: Create admin user
    admin_credentials = create_admin_user()
    if admin_credentials:
        success_count += 1
    
    # Step 3: Setup GCS
    if setup_gcs_buckets():
        success_count += 1
    
    # Display results
    if success_count == total_steps:
        display_setup_summary(admin_credentials)
        print("\n✅ Setup completed successfully!")
        return 0
    else:
        print(f"\n❌ Setup completed with {total_steps - success_count} errors")
        print("Please check the logs above and resolve any issues")
        return 1


if __name__ == '__main__':
    sys.exit(main())
