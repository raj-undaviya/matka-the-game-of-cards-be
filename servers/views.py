import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone

from .services import AWSServerService
from .models import GameServer
from .services import AWSServerService
import logging
 
 
aws_service = AWSServerService()
logger = logging.getLogger(__name__)
 
 
@method_decorator(staff_member_required, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class DeployArenaView(View):
    """
    POST /admin/api/deploy-arena/
    Modal ka "Deploy Instance" button yahan hit karta hai
    """
 
    def post(self, request):
        try:
            data = json.loads(request.body)
 
            # Validate
            required = ["arena_name", "region", "max_players", "risk_profile", "liquidity_seed"]
            for field in required:
                if not data.get(field):
                    return JsonResponse({"error": f"{field} is required"}, status=400)
 
            # Arena name unique check
            if GameServer.objects.filter(arena_name=data["arena_name"]).exists():
                return JsonResponse({"error": "Arena name already exists"}, status=400)
 
            # 1. DB mein save karo (status=launching)
            server = GameServer.objects.create(
                arena_name     = data["arena_name"],
                region         = data["region"],
                max_players    = int(data["max_players"]),
                risk_profile   = data["risk_profile"],
                liquidity_seed = float(data["liquidity_seed"]),
                status         = GameServer.Status.LAUNCHING,
                created_by     = request.user,
            )
 
            # 2. AWS mein instance banao
            aws_result = aws_service.create_instance(server)
 
            # 3. DB update karo AWS details ke saath
            server.instance_id    = aws_result["instance_id"]
            server.instance_type  = aws_result["instance_type"]
            server.private_ip     = aws_result.get("private_ip")
            server.status         = GameServer.Status.WARMING
            server.save()
 
            return JsonResponse({
                "success":     True,
                "server_id":   server.id,
                "instance_id": server.instance_id,
                "arena_name":  server.arena_name,
                "status":      server.status,
                "message":     f"Instance {server.instance_id} deploying..."
            }, status=201)
 
        except Exception as e:
            logger.error(f"Deploy failed: {e}")
            if "server" in locals():
                server.status = GameServer.Status.FAILED
                server.save()
            return JsonResponse({"error": str(e)}, status=500)
 
 
@method_decorator(staff_member_required, name="dispatch")
class ServerListView(View):
    """
    GET /admin/api/servers/
    Admin panel ka server list + health status
    """
 
    def get(self, request):
        servers = GameServer.objects.exclude(
            status=GameServer.Status.TERMINATED
        ).values(
            "id", "arena_name", "region", "status",
            "latency_ms", "public_ip", "instance_id",
            "instance_type", "max_players", "risk_profile",
            "created_at"
        )
        return JsonResponse({"servers": list(servers)})
 
 
@method_decorator(staff_member_required, name="dispatch")
class ServerStatusView(View):
    """
    GET /admin/api/servers/<server_id>/status/
    Real-time AWS se status fetch karo — polling ke liye
    """
 
    def get(self, request, server_id):
        try:
            server = GameServer.objects.get(id=server_id)
 
            if not server.instance_id:
                return JsonResponse({"error": "No instance yet"}, status=400)
 
            # AWS se live status lo
            aws_status = aws_service.get_instance_status(
                server.instance_id, server.region
            )
 
            # DB update karo
            server.status     = aws_status["status"]
            server.latency_ms = aws_status["latency_ms"]
            if aws_status.get("public_ip"):
                server.public_ip = aws_status["public_ip"]
            server.save(update_fields=["status", "latency_ms", "public_ip", "updated_at"])
 
            return JsonResponse({
                "server_id":   server.id,
                "arena_name":  server.arena_name,
                "instance_id": server.instance_id,
                "region":      server.display_region,
                "status":      server.status,
                "latency_ms":  server.latency_ms,
                "public_ip":   server.public_ip,
            })
 
        except GameServer.DoesNotExist:
            return JsonResponse({"error": "Server not found"}, status=404)
 
 
@method_decorator(staff_member_required, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class ServerActionView(View):
    """
    POST /admin/api/servers/<server_id>/action/
    Body: {"action": "stop" | "start" | "terminate"}
    """
 
    def post(self, request, server_id):
        try:
            server = GameServer.objects.get(id=server_id)
            data   = json.loads(request.body)
            action = data.get("action")
 
            if action == "stop":
                aws_service.stop_instance(server.instance_id, server.region)
                server.status = GameServer.Status.STOPPING
 
            elif action == "start":
                aws_service.start_instance(server.instance_id, server.region)
                server.status = GameServer.Status.WARMING
 
            elif action == "terminate":
                aws_service.terminate_instance(server.instance_id, server.region)
                server.status       = GameServer.Status.TERMINATED
                server.terminated_at = timezone.now()
 
            else:
                return JsonResponse({"error": "Invalid action"}, status=400)
 
            server.save()
            return JsonResponse({"success": True, "status": server.status})
 
        except GameServer.DoesNotExist:
            return JsonResponse({"error": "Server not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
 
 
@method_decorator(staff_member_required, name="dispatch")
class AllServersHealthView(View):
    """
    GET /admin/api/servers/health/
    Saare AWS servers ka live health — image jaisi list
    """
 
    def get(self, request):
        health_data = aws_service.list_all_servers_health()
        return JsonResponse({"servers": health_data})
 
 