"""
game/routing.py
================
Django Channels — WebSocket URL routing
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/rounds/$", consumers.RoundsConsumer.as_asgi()),
]