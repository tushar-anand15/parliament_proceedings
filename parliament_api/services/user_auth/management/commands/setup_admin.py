from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = 'Create admin user and setup initial authentication'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default=settings.ADMIN_USERNAME,
            help='Admin username'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=settings.ADMIN_PASSWORD,
            help='Admin password'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=settings.ADMIN_EMAIL,
            help='Admin email'
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']

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
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created admin user: {username}')
            )
        else:
            # Update password and permissions
            user.set_password(password)
            user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully updated admin user: {username}')
            )

        # Create or get auth token
        token, token_created = Token.objects.get_or_create(user=user)
        
        if token_created:
            self.stdout.write(
                self.style.SUCCESS(f'Created auth token: {token.key}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Existing auth token: {token.key}')
            )

        # Display credentials
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('ADMIN CREDENTIALS'))
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write(f'Username: {username}')
        self.stdout.write(f'Password: {password}')
        self.stdout.write(f'Email: {email}')
        self.stdout.write(f'Auth Token: {token.key}')
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write(self.style.WARNING('Please save these credentials securely!'))
