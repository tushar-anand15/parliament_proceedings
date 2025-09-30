from django.apps import AppConfig


class FilesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.files"
    verbose_name = "File Management"
    
    def ready(self):
        """Import tasks when app is ready to ensure Celery autodiscovery works"""
        try:
            # Import task modules to register them with Celery
            from . import tasks  # Unified PDF tasks
        except ImportError:
            pass