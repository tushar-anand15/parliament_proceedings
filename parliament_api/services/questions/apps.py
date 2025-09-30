from django.apps import AppConfig


class QuestionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.questions"
    verbose_name = "Parliamentary Questions"
    
    def ready(self):
        """Import tasks when app is ready to ensure Celery autodiscovery works"""
        try:
            # Import all task modules to register them with Celery (now includes RS tasks)
            from . import tasks  # LS + RS tasks (integrated)
        except ImportError:
            pass