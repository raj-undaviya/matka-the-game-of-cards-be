import os
import django
import random
import time
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matka_the_game_of_cards.settings')
django.setup()

from django.conf import settings
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

from django.contrib.auth import get_user_model
from game.models import Game, Pool, Round, Bet, PoolParticipant
from game.services import PoolService, RoundService, WalletService
from wallet.models import Wallet

User = get_user_model()


def run_simulation():
    print("=" * 60)
    print("STARTING MATKA POOL SIMULATION")
    print("=" * 60)

    # 1. Create or retrieve admin user (to create game/pools)
    admin_user, created = User.objects.get_or_create(
        username='simulation_admin',
        defaults={'email': 'admin@matka.com', 'is_staff': True, 'is_superuser': True}
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        print("Created simulation admin user.")

    # 2. Create 100 test users and fund their wallets
    print("\nCreating and funding 100 test users...")
    test_users = []
    for i in range(1, 101):
        username = f"test_user_{i}"
        email = f"user_{i}@matka.com"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': email}
        )
        if created:
            user.set_password('password123')
            user.save()

        # Ensure wallet exists and has balance
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.balance = Decimal("1000.00")
        wallet.save()
        test_users.append(user)

    print("Successfully initialized 100 test users with ₹1000 each in their wallets.")

    # 3. Create Game
    print("\nSetting up Game and Pool...")
    game, created = Game.objects.get_or_create(
        name="Simulation Single Game",
        variation="V1",
        defaults={'description': 'V1 Single variation for automated testing'}
    )
    if created:
        print(f"Created Game: {game.name}")
    else:
        print(f"Using existing Game: {game.name}")

    # 4. Create Pool
    pool = Pool.objects.create(
        game=game,
        name=f"Automated Testing Pool - Fee ₹10",
        entry_fee=10,
        max_players=100,
        rounds_count=10,
        round_duration_seconds=1,
        status=Pool.Status.UPCOMING
    )
    print(f"Created Pool: {pool.name} (ID: {pool.id})")

    # 5. Join 100 users to the pool (in bulk to prevent slow network roundtrips)
    print("\nSimulating 100 users joining the pool in bulk...")
    from django.db import models
    from wallet.models import Transaction
    
    # Bulk create participants
    participants = [PoolParticipant(pool=pool, user=user) for user in test_users]
    PoolParticipant.objects.bulk_create(participants)
    
    # Bulk update wallet balances
    user_ids = [u.id for u in test_users]
    Wallet.objects.filter(user_id__in=user_ids).update(balance=models.F('balance') - Decimal("10.00"))
    
    # Bulk create transaction audit logs
    wallets = {w.user_id: w for w in Wallet.objects.filter(user_id__in=user_ids)}
    transactions = [
        Transaction(
            wallet=wallets[user.id],
            transaction_type='bet_debit',
            amount=Decimal("10.00"),
            balance_before=Decimal("1000.00"),
            balance_after=Decimal("990.00"),
            status='success',
            reference=f"pool_join:{pool.id}",
            note=f"Joined pool {pool.name} (Entry fee: ₹10)"
        )
        for user in test_users
    ]
    Transaction.objects.bulk_create(transactions)

    pool.refresh_from_db()
    print(f"Pool size: {pool.participants.count()} participants. Total collected pool: ₹{pool.entry_fee * pool.participants.count()}")

    # 6. Start the pool
    print("\nStarting the Pool (opening Round 1)...")
    success = PoolService.start_pool(pool.id)
    if not success:
        print("Failed to start pool.")
        return

    # Loop through rounds
    for r_num in range(1, pool.rounds_count + 1):
        print("\n" + "-" * 50)
        print(f"ROUND {r_num} / {pool.rounds_count}")
        print("-" * 50)

        # Get current active round for the pool
        round_obj = pool.rounds.get(round_number=r_num, status=Round.Status.BETTING_OPEN)
        print(f"Active Round ID: {round_obj.id}")

        # Place bets for all 100 participants
        placed_bets_count = 0
        for user in test_users:
            selected = [random.randint(1, 10)]
            success, res = RoundService.place_bet(
                round_id=str(round_obj.id),
                user=user,
                selected_numbers=selected,
                entry_fee=round_obj.config.entry_fee
            )
            if success:
                placed_bets_count += 1
            else:
                print(f"Failed to place bet for {user.username}: {res}")

        print(f"Placed {placed_bets_count} bets successfully in Round {r_num}.")

        # Trigger draw for the round
        print(f"Triggering draw for Round {r_num}...")
        RoundService._trigger_draw(round_obj, client_seed=f"sim_round_{r_num}")

        round_obj.refresh_from_db()
        print(f"Round {r_num} completed. Drawn number: {round_obj.drawn_numbers}")
        
        winners = round_obj.winners_data.get('winners', [])
        print(f"Winners in this round: {len(winners)}")

        # Print current leaderboard top 5
        print("\nCurrent Leaderboard standings (Top 5):")
        standings = pool.participants.all().order_by('rank', '-total_points')[:5]
        for part in standings:
            print(f"Rank {part.rank}: {part.user.username} | Points: {part.total_points}")

        time.sleep(1)

    print("\n" + "=" * 60)
    print("SIMULATION COMPLETED!")
    print("=" * 60)

    # Refresh pool and print final results
    pool.refresh_from_db()
    print(f"Pool status: {pool.status}")
    print("\nFinal Winners (Top 3 payouts):")
    winners = pool.participants.all().order_by('rank')[:3]
    for part in winners:
        print(f"Rank {part.rank}: {part.user.username} | Total Points: {part.total_points} | Prize Won: ₹{part.reward_paid}")

    print("\nChecking wallets of Top 3 Winners:")
    for part in winners:
        wallet = Wallet.objects.get(user=part.user)
        print(f"{part.user.username} wallet balance: ₹{wallet.balance} (Started with ₹1000, joined with -₹10)")


if __name__ == '__main__':
    run_simulation()
