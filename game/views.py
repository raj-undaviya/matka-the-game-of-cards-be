"""
Matka Game — DRF Views
========================
Endpoints:
  GET  /api/rounds/                  → open rounds list
  POST /api/rounds/create/           → new round (admin only)
  GET  /api/rounds/<id>/             → round detail
  POST /api/bets/place/              → place a bet
  GET  /api/bets/my/                 → my bets
  GET  /api/wallet/                  → my wallet balance
  GET  /api/wallet/transactions/     → my transaction history
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404

from .models import Round, Bet
from wallet.models import Wallet, Transaction
from .serializers import (
    RoundListSerializer, RoundDetailSerializer,
    PlaceBetSerializer, BetSerializer
)
from wallet.serializers import WalletSerializer, TransactionSerializer
from .services import RoundService, WalletService


class RoundListView(APIView):
    """GET /api/rounds/ — betting open rounds"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        variation = request.query_params.get('variation')
        qs = Round.objects.filter(status=Round.Status.BETTING_OPEN)
        if variation:
            qs = qs.filter(variation=variation)
        serializer = RoundListSerializer(qs, many=True)
        return Response(serializer.data)


class RoundCreateView(APIView):
    """POST /api/rounds/create/ — admin only"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        variation = request.data.get('variation')
        valid_variations = [v.value for v in __import__(
            'core.game_engine', fromlist=['GameVariation']
        ).GameVariation]

        if variation not in valid_variations:
            return Response(
                {"error": f"Invalid variation. Choose from: {valid_variations}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        round_obj = RoundService.create_round(variation)
        return Response(
            RoundListSerializer(round_obj).data,
            status=status.HTTP_201_CREATED
        )


class RoundDetailView(APIView):
    """GET /api/rounds/<id>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, round_id):
        round_obj = get_object_or_404(Round, id=round_id)
        serializer = RoundDetailSerializer(round_obj)
        return Response(serializer.data)


class PlaceBetView(APIView):
    """POST /api/bets/place/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PlaceBetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        success, result = RoundService.place_bet(
            round_id=str(data['round_id']),
            user=request.user,
            selected_numbers=data['selected_numbers'],
            entry_fee=data['entry_fee']
        )

        if not success:
            return Response({"error": result}, status=status.HTTP_400_BAD_REQUEST)

        # result is bet_id on success
        bet = Bet.objects.get(id=result)
        return Response(BetSerializer(bet).data, status=status.HTTP_201_CREATED)


class MyBetsView(APIView):
    """GET /api/bets/my/ — logged in user ke bets"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bets = Bet.objects.filter(user=request.user).select_related('round')
        serializer = BetSerializer(bets, many=True)
        return Response(serializer.data)


class WalletView(APIView):
    """GET /api/wallet/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = WalletService.get_or_create(request.user)
        return Response(WalletSerializer(wallet).data)


class WalletTransactionView(APIView):
    """GET /api/wallet/transactions/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = WalletService.get_or_create(request.user)
        txs = Transaction.objects.filter(wallet=wallet)[:50]
        return Response(TransactionSerializer(txs, many=True).data)