from django.apps import AppConfig


class WalletConfig(AppConfig):
    name = 'wallet'
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
