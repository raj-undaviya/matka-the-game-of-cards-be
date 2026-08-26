from django.apps import AppConfig


class ServersConfig(AppConfig):
    name = 'servers'
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
