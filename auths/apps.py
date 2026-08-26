from django.apps import AppConfig


class AuthsConfig(AppConfig):
    name = 'auths'
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
