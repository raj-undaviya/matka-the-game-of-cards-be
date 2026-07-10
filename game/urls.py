"""
game/urls.py  (UPDATED)
========================
Apne main urls.py mein add karo:
  path('api/', include('game.urls')),

WebSocket (asgi.py mein add karo):
  from game.routing import websocket_urlpatterns
"""
from django.urls import path
from .views import (
    # User APIs
    RoundListView, RoundCreateView, RoundDetailView,
    PlaceBetView, MyBetsView,
    WalletView, WalletTransactionView,

    # Admin APIs
    AdminDashboardView,
    AdminGamesView,
    AdminRoundListView, AdminRoundDetailView, AdminForceDrawView,
    AdminUserListView, AdminUserDetailView, AdminWalletAdjustView,
    AdminTransactionListView,

    # Dynamic Games & Pools APIs
    AdminGameCreateView,
    AdminPoolCreateView,
    AdminPoolStartView,
    PoolListView,
    PoolJoinView,
    PoolLeaderboardView,
)

urlpatterns = [

    # ── User APIs ──────────────────────────────────────────────────
    path('rounds/',                   RoundListView.as_view(),   name='round-list'),
    path('rounds/create/',            RoundCreateView.as_view(), name='round-create'),
    path('rounds/<uuid:round_id>/',   RoundDetailView.as_view(), name='round-detail'),

    path('bets/place/',               PlaceBetView.as_view(),    name='bet-place'),
    path('bets/my/',                  MyBetsView.as_view(),      name='my-bets'),

    path('wallet/',                   WalletView.as_view(),             name='wallet'),
    path('wallet/transactions/',      WalletTransactionView.as_view(),  name='wallet-txns'),

    # ── Dynamic Pools User APIs ────────────────────────────────────
    path('pools/',                    PoolListView.as_view(),            name='pool-list'),
    path('pools/<int:pool_id>/join/', PoolJoinView.as_view(),            name='pool-join'),
    path('pools/<int:pool_id>/leaderboard/', PoolLeaderboardView.as_view(), name='pool-leaderboard'),

    # ── Admin APIs ─────────────────────────────────────────────────
    path('admin/dashboard/',          AdminDashboardView.as_view(),     name='admin-dashboard'),
    path('admin/games/',              AdminGamesView.as_view(),         name='admin-games'),
    path('admin/games/create/',       AdminGameCreateView.as_view(),    name='admin-game-create'),
    path('admin/pools/create/',       AdminPoolCreateView.as_view(),    name='admin-pool-create'),
    path('admin/pools/<int:pool_id>/start/', AdminPoolStartView.as_view(), name='admin-pool-start'),

    path('admin/rounds/',             AdminRoundListView.as_view(),     name='admin-round-list'),
    path('admin/rounds/<uuid:round_id>/',       AdminRoundDetailView.as_view(), name='admin-round-detail'),
    path('admin/rounds/<uuid:round_id>/force-draw/', AdminForceDrawView.as_view(),   name='admin-force-draw'),

    path('admin/users/',              AdminUserListView.as_view(),      name='admin-user-list'),
    path('admin/users/<int:user_id>/',          AdminUserDetailView.as_view(),  name='admin-user-detail'),
    path('admin/users/<int:user_id>/adjust-wallet/', AdminWalletAdjustView.as_view(), name='admin-adjust-wallet'),

    path('admin/transactions/',       AdminTransactionListView.as_view(), name='admin-transactions'),
]