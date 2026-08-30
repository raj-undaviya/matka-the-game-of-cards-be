from django.urls import path
from .views import (
    AdminMarkPaidView,
    AdminWithdrawListView,
    WalletBalanceView,
    DepositInitView,
    DepositVerifyView,
    WithdrawRequestView,
    AdminWithdrawActionView,
    TransactionHistoryView,
)

urlpatterns = [
    # User APIs
    path("balance/",        WalletBalanceView.as_view(),      name="wallet-balance"),
    path("deposit/init/",   DepositInitView.as_view(),        name="wallet-deposit-init"),
    path("deposit/verify/", DepositVerifyView.as_view(),      name="wallet-deposit-verify"),
    path("withdraw/",       WithdrawRequestView.as_view(),    name="wallet-withdraw"),
    path("transactions/",   TransactionHistoryView.as_view(), name="wallet-transactions"),

    # Admin APIs
    path("admin-panel/withdraws/",              AdminWithdrawListView.as_view(),          name="admin-withdraw-list"),
    path("admin-panel/withdraws/<str:pk>/action/", AdminWithdrawActionView.as_view(),     name="admin-withdraw-action"),
    path("admin-panel/withdraws/<str:pk>/mark-paid/", AdminMarkPaidView.as_view(), name="admin-mark-paid"),
]