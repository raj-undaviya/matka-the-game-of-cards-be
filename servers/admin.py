from django.contrib import admin as django_admin
from .models import *
from .services import *
 
@django_admin.register(GameServer)
class GameServerAdmin(django_admin.ModelAdmin):
    list_display = [
        "arena_name", "region", "status",
        "latency_ms", "public_ip", "instance_type",
        "max_players", "risk_profile", "created_at"
    ]
    list_filter  = ["status", "region", "risk_profile"]
    search_fields = ["arena_name", "instance_id"]
    readonly_fields = [
        "instance_id", "public_ip", "private_ip",
        "instance_type", "created_at", "updated_at", "terminated_at"
    ]
 
    # Admin console se bhi actions le sako
    actions = ["stop_selected_servers", "terminate_selected_servers"]
 
    def stop_selected_servers(self, request, queryset):
        svc = AWSServerService()
        for server in queryset.filter(status=GameServer.Status.HEALTHY):
            svc.stop_instance(server.instance_id, server.region)
            server.status = GameServer.Status.STOPPING
            server.save()
    stop_selected_servers.short_description = "Stop selected servers"
 
    def terminate_selected_servers(self, request, queryset):
        svc = AWSServerService()
        for server in queryset.exclude(status=GameServer.Status.TERMINATED):
            svc.terminate_instance(server.instance_id, server.region)
            server.status = GameServer.Status.TERMINATED
            server.save()
    terminate_selected_servers.short_description = "Terminate selected servers"