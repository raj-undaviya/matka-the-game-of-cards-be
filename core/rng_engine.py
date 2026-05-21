"""
Provably Fair RNG Engine
========================
Koi bhi result predict ya manipulate nahi kar sakta.

How it works:
  BEFORE round: server commits SHA256(server_seed) → user dekh sakta hai
  AFTER  round: server reveals server_seed → user verify kar sakta hai
  Result      : HMAC-SHA256(server_seed, client_seed + round_id + nonce)
"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SeedCommitment:
    """Round shuru hone se pehle server ye hash user ko deta hai"""
    round_id: str
    server_seed_hash: str      # SHA256(server_seed) — publicly shared
    created_at: str
    # server_seed is NEVER shared until round ends


@dataclass
class RevealedSeed:
    """Round khatam hone ke baad seed reveal hoti hai — user verify kar sakta hai"""
    round_id: str
    server_seed: str           # Actual seed — now revealed
    server_seed_hash: str      # Should match what was committed
    client_seed: str
    winning_numbers: list
    verification_string: str   # How to independently verify


class ProvablyFairRNG:

    @staticmethod
    def generate_server_seed() -> str:
        """256-bit cryptographically secure random seed"""
        return secrets.token_hex(32)  # 64 hex chars = 256 bits

    @staticmethod
    def hash_seed(seed: str) -> str:
        """Commit hash — shared with users BEFORE draw"""
        return hashlib.sha256(seed.encode()).hexdigest()

    @staticmethod
    def verify_seed(seed: str, committed_hash: str) -> bool:
        """User/anyone can verify server didn't change the seed"""
        return hashlib.sha256(seed.encode()).hexdigest() == committed_hash

    @staticmethod
    def generate_numbers(
        server_seed: str,
        client_seed: str,
        round_id: str,
        count: int = 1,
        card_range: int = 10
    ) -> list:
        """
        HMAC-SHA256 based deterministic number generation.
        Same inputs → same outputs → fully verifiable.
        """
        combined = f"{client_seed}:{round_id}"
        numbers = []
        for i in range(count):
            nonce = f"{combined}:{i}"
            hmac_hash = hmac.new(
                server_seed.encode(),
                nonce.encode(),
                hashlib.sha256
            ).hexdigest()
            hex_segment = hmac_hash[:8]
            number = (int(hex_segment, 16) % card_range) + 1
            numbers.append(number)
        return numbers

    @classmethod
    def create_commitment(cls, round_id: str):
        """
        Step 1: Round shuru hone se pehle call karo
        Returns: (secret_seed, public_commitment)
        secret_seed ko DB mein encrypt karke store karo — API se KABHI expose mat karo
        """
        server_seed = cls.generate_server_seed()
        commitment = SeedCommitment(
            round_id=round_id,
            server_seed_hash=cls.hash_seed(server_seed),
            created_at=datetime.utcnow().isoformat()
        )
        return server_seed, commitment

    @classmethod
    def reveal_and_draw(
        cls,
        server_seed: str,
        commitment: SeedCommitment,
        client_seed: str,
        draw_count: int
    ) -> RevealedSeed:
        """
        Step 2: Round khatam hone par call karo
        """
        winning_numbers = cls.generate_numbers(
            server_seed, client_seed, commitment.round_id, draw_count
        )
        return RevealedSeed(
            round_id=commitment.round_id,
            server_seed=server_seed,
            server_seed_hash=commitment.server_seed_hash,
            client_seed=client_seed,
            winning_numbers=winning_numbers,
            verification_string=(
                f"Verify: SHA256('{server_seed}') == '{commitment.server_seed_hash}'\n"
                f"Result: HMAC-SHA256(server_seed, '{client_seed}:{commitment.round_id}:N')"
            )
        )