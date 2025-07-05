from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.user_auth"
    verbose_name = "Authentication & User Management"
