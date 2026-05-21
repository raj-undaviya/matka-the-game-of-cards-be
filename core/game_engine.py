"""
Game Engine — Har Variation ka Winning Logic
=============================================
V1 Single:     1 draw,  match 1 number         → x10
V2 Pair:       2 draws, match both in order    → x20
V3 Trio:       3 draws, triple=big/any=small   → x50 / x25
V4 Sum Matka:  3 draws, sum last digit match   → x80
V5 Jackpot:    1 draw,  lucky one winner       → whole pool
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .rng_engine import ProvablyFairRNG, SeedCommitment


class GameVariation(Enum):
    SINGLE     = "V1"
    PAIR       = "V2"
    TRIO       = "V3"
    SUM_MATKA  = "V4"   # Last digit sum game
    JACKPOT    = "V5"


@dataclass
class GameConfig:
    variation: GameVariation
    entry_fee: int
    max_slots: int
    draw_count: int
    reward_multiplier: float
    reward_multiplier_small: float = 0.0  # V3 partial win


GAME_CONFIGS = {
    GameVariation.SINGLE:    GameConfig(GameVariation.SINGLE,    100,  5, 1, 10.0),
    GameVariation.PAIR:      GameConfig(GameVariation.PAIR,       150,  5, 2, 20.0),
    GameVariation.TRIO:      GameConfig(GameVariation.TRIO,       200,  5, 3, 50.0, 25.0),
    GameVariation.SUM_MATKA: GameConfig(GameVariation.SUM_MATKA, 1000, 5, 3, 80.0),
    GameVariation.JACKPOT:   GameConfig(GameVariation.JACKPOT,      0, 10, 1,  0.0),
}


@dataclass
class BetRecord:
    user_id: str
    round_id: str
    variation: GameVariation
    selected_numbers: list   # V1:[6], V2:[3,7], V3:[5,5,5], V4:[2], V5:[8]
    entry_fee: int
    bet_id: str


@dataclass
class RoundResult:
    round_id: str
    variation: GameVariation
    drawn_numbers: list
    winners: list            # [{user_id, reward_amount, win_type}]
    total_pool: int
    verified_seed: dict      # Provably fair proof


class GameEngine:

    def validate_bet(self, bet: BetRecord):
        """
        Bet valid hai ya nahi — sab rules check karo
        Returns: (is_valid: bool, message: str)
        """
        config = GAME_CONFIGS[bet.variation]

        # Number range: 1-10 only (A=1, 2-9, 10)
        for num in bet.selected_numbers:
            if num < 1 or num > 10:
                return False, f"Invalid number {num}. Choose 1-10 only (A=1, cards 2-10)."

        # Each variation needs specific count of numbers
        required = {
            GameVariation.SINGLE:    1,
            GameVariation.PAIR:      2,
            GameVariation.TRIO:      3,
            GameVariation.SUM_MATKA: 1,
            GameVariation.JACKPOT:   1,
        }
        req = required[bet.variation]
        if len(bet.selected_numbers) != req:
            return False, f"{bet.variation.name} requires exactly {req} number(s)."

        # Entry fee validation
        if bet.variation != GameVariation.JACKPOT:
            if bet.entry_fee != config.entry_fee:
                return False, f"Entry fee must be exactly {config.entry_fee}."
        elif bet.entry_fee < 1:
            return False, "Jackpot minimum entry is 1."

        return True, "OK"

    def calculate_winner(
        self,
        variation: GameVariation,
        bet: BetRecord,
        drawn_numbers: list,
        total_pool: int = 0
    ) -> Optional[dict]:
        """
        Core winning check — har variation alag
        Returns: {win_type, reward_amount} or None
        """
        config = GAME_CONFIGS[variation]

        # ------- V1: Single -------
        if variation == GameVariation.SINGLE:
            if bet.selected_numbers[0] == drawn_numbers[0]:
                return {
                    "win_type": "single_match",
                    "reward_amount": int(bet.entry_fee * config.reward_multiplier)
                }

        # ------- V2: Pair -------
        elif variation == GameVariation.PAIR:
            # Order matters: open card = index 0, close card = index 1
            if (bet.selected_numbers[0] == drawn_numbers[0] and
                    bet.selected_numbers[1] == drawn_numbers[1]):
                return {
                    "win_type": "pair_match",
                    "reward_amount": int(bet.entry_fee * config.reward_multiplier)
                }

        # ------- V3: Trio -------
        elif variation == GameVariation.TRIO:
            all_same = (drawn_numbers[0] == drawn_numbers[1] == drawn_numbers[2])

            if all_same:
                triple_num = drawn_numbers[0]
                # Big win: user ne triple hi select kiya AND drawn triple match karta hai
                if all(n == triple_num for n in bet.selected_numbers):
                    return {
                        "win_type": "trio_triple_win",
                        "reward_amount": int(bet.entry_fee * config.reward_multiplier)
                    }
            else:
                # Small win: drawn numbers mein se koi bhi user ke 3 selections se match kare
                drawn_set = set(drawn_numbers)
                user_set = set(bet.selected_numbers)
                if drawn_set & user_set:
                    return {
                        "win_type": "trio_partial_win",
                        "reward_amount": int(bet.entry_fee * config.reward_multiplier_small)
                    }

        # ------- V4: Sum Matka (Last Digit Sum) -------
        elif variation == GameVariation.SUM_MATKA:
            total_sum = sum(drawn_numbers)
            last_digit = total_sum % 10
            if bet.selected_numbers[0] == last_digit:
                return {
                    "win_type": "sum_last_digit_match",
                    "reward_amount": int(bet.entry_fee * config.reward_multiplier),
                    "sum_details": {
                        "cards": drawn_numbers,
                        "total": total_sum,
                        "last_digit": last_digit
                    }
                }

        # ------- V5: Jackpot — caller handles winner selection -------
        elif variation == GameVariation.JACKPOT:
            return {"win_type": "jackpot_candidate", "reward_amount": 0}

        return None  # No win

    def resolve_round(
        self,
        round_id: str,
        variation: GameVariation,
        bets: list,
        server_seed: str,
        commitment: SeedCommitment,
        client_seed: str = "default"
    ) -> RoundResult:
        """
        Round resolve karo — draw karo, winners nikalo, rewards compute karo
        """
        config = GAME_CONFIGS[variation]

        # Provably fair draw
        reveal = ProvablyFairRNG.reveal_and_draw(
            server_seed, commitment, client_seed, config.draw_count
        )
        drawn_numbers = reveal.winning_numbers

        total_pool = sum(b.entry_fee for b in bets)
        winners = []

        if variation == GameVariation.JACKPOT:
            # V5: Drawn number ko index ke roop mein use karke ek winner
            if bets:
                winner_index = drawn_numbers[0] % len(bets)
                winner_bet = bets[winner_index]
                winners.append({
                    "user_id": winner_bet.user_id,
                    "win_type": "jackpot_winner",
                    "reward_amount": total_pool,
                    "entry_fee_paid": winner_bet.entry_fee
                })
        else:
            for bet in bets:
                result = self.calculate_winner(variation, bet, drawn_numbers, total_pool)
                if result:
                    result["user_id"] = bet.user_id
                    result["entry_fee_paid"] = bet.entry_fee
                    winners.append(result)

        return RoundResult(
            round_id=round_id,
            variation=variation,
            drawn_numbers=drawn_numbers,
            winners=winners,
            total_pool=total_pool,
            verified_seed={
                "server_seed": reveal.server_seed,
                "server_seed_hash": reveal.server_seed_hash,
                "client_seed": reveal.client_seed,
                "how_to_verify": reveal.verification_string
            }
        )