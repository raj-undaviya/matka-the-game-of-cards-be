"""
game/consumers.py
==================
Django Channels — Real-time Slot Count Updates

Setup:
  pip install channels channels-redis

settings.py mein add karo:
  INSTALLED_APPS += ['channels']

  CHANNEL_LAYERS = {
      "default": {
          "BACKEND": "channels_redis.core.RedisChannelLayer",
          "CONFIG": {"hosts": [("127.0.0.1", 6379)]},
      }
  }

  # ASGI_APPLICATION setting:
  ASGI_APPLICATION = "your_project.asgi.application"

asgi.py mein add karo:
  from channels.routing import ProtocolTypeRouter, URLRouter
  from channels.auth import AuthMiddlewareStack
  from game.routing import websocket_urlpatterns

  application = ProtocolTypeRouter({
      "http": get_asgi_application(),
      "websocket": AuthMiddlewareStack(
          URLRouter(websocket_urlpatterns)
      ),
  })

Frontend se connect karo:
  const ws = new WebSocket("ws://localhost:8000/ws/rounds/");
  ws.onmessage = (e) => console.log(JSON.parse(e.data));
"""
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)

# Sabhi connected clients ka shared group name
ROUNDS_GROUP = "rounds_lobby"


class RoundsConsumer(AsyncWebsocketConsumer):
    """
    Ek single WebSocket channel — sabhi open rounds ka live snapshot.

    Connect hone pe:
      - Current sab open rounds ka slot count bhejta hai (initial state)

    Jab bhi koi bet place ho:
      - services.py notify_slot_update() call karta hai
      - Yeh consumer updated round data push karta hai sabko
    """

    async def connect(self):
        await self.channel_layer.group_add(ROUNDS_GROUP, self.channel_name)
        await self.accept()

        # Connect hote hi current state bhejo
        snapshot = await self.get_rounds_snapshot()
        await self.send(text_data=json.dumps({
            "type": "snapshot",
            "rounds": snapshot
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(ROUNDS_GROUP, self.channel_name)

    # ── Server-side push — services.py se aata hai ──────────────────
    async def slot_update(self, event):
        """
        Jab koi slot fill ho — sab connected clients ko update bhejo.
        event keys: round_id, variation, slots_filled, slots_available, status
        """
        await self.send(text_data=json.dumps({
            "type": "slot_update",
            "round_id":       event["round_id"],
            "variation":      event["variation"],
            "slots_filled":   event["slots_filled"],
            "slots_available": event["slots_available"],
            "status":         event["status"],
        }))

    # ── DB call — sync to async ──────────────────────────────────────
    @database_sync_to_async
    def get_rounds_snapshot(self):
        from .models import Round
        from core.game_engine import GAME_CONFIGS, GameVariation

        rounds = Round.objects.filter(status=Round.Status.BETTING_OPEN)
        result = []
        for r in rounds:
            try:
                config = GAME_CONFIGS[GameVariation(r.variation)]
                result.append({
                    "round_id":        str(r.id),
                    "variation":       r.variation,
                    "slots_filled":    r.slots_filled,
                    "slots_available": r.slots_available,
                    "max_slots":       config.max_slots,
                    "entry_fee":       config.entry_fee,
                    "status":          r.status,
                })
            except Exception as e:
                logger.error(f"Snapshot error for round {r.id}: {e}")
        return result