from django.contrib import admin
from .models import Wallet, Transaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "balance", "created_at"]

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["wallet", "transaction_type", "amount", "status", "created_at"]
    list_filter  = ["transaction_type", "status"]