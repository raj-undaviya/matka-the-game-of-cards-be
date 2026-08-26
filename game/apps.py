from django.apps import AppConfig


class GameConfig(AppConfig):
    name = 'game'
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
