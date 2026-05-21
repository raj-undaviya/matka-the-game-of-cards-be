"""
Matka Game — URL Configuration
================================
Apne main urls.py mein add karo:
  path('api/', include('matka.urls')),
"""
from django.urls import path
from .views import (
    RoundListView, RoundCreateView, RoundDetailView,
    PlaceBetView, MyBetsView,
    WalletView, WalletTransactionView
)

urlpatterns = [
    # Rounds
    path('rounds/',          RoundListView.as_view(),   name='round-list'),
    path('rounds/create/',   RoundCreateView.as_view(), name='round-create'),
    path('rounds/<uuid:round_id>/', RoundDetailView.as_view(), name='round-detail'),

    # Bets
    path('bets/place/',      PlaceBetView.as_view(),    name='bet-place'),
    path('bets/my/',         MyBetsView.as_view(),      name='my-bets'),

    # Wallet
    path('wallet/',          WalletView.as_view(),          name='wallet'),
    path('wallet/transactions/', WalletTransactionView.as_view(), name='wallet-txns'),
]