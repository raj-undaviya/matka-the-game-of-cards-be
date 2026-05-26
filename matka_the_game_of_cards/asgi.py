"""
ASGI config for matka_the_game_of_cards project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from game.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matka_the_game_of_cards.settings')

application = ProtocolTypeRouter({
    # Normal HTTP requests — Django handle karega as usual
    "http": get_asgi_application(),

    # WebSocket requests — Channels handle karega
    # AuthMiddlewareStack: JWT/session se user automatically scope mein aa jaata hai
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
