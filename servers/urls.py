from django.urls import path
from .views import *
 
urlpatterns = [
    path("deploy-arena/",              DeployArenaView.as_view(),    name="deploy-arena"),
    path("servers/",                   ServerListView.as_view(),     name="server-list"),
    path("servers/health/",            AllServersHealthView.as_view(),name="servers-health"),
    path("servers/<int:server_id>/status/", ServerStatusView.as_view(),  name="server-status"),
    path("servers/<int:server_id>/action/", ServerActionView.as_view(),  name="server-action"),
]
 
 