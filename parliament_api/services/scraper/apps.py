from django.apps import AppConfig


class ScraperConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'services.scraper'
    verbose_name = 'Parliamentary Data Scraper' 