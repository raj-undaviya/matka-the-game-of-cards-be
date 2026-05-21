"""
Matka Game — Celery Tasks
==========================
V5 Jackpot ke liye timer-based auto draw.

Setup:
  pip install celery redis django-celery-beat

settings.py mein add karo:
  CELERY_BROKER_URL = 'redis://localhost:6379/0'
  INSTALLED_APPS += ['django_celery_beat']
"""
from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def trigger_jackpot_draw(self, round_id: str):
    """
    V5 Jackpot round draw karo.
    Yeh task round create hone ke 10 min (testing) / 5 hr (prod) baad schedule hoti hai.
    """
    try:
        from .services import RoundService
        result = RoundService.trigger_jackpot_draw(round_id)
        if result:
            return f"Jackpot drawn for round {round_id}. Winners: {len(result.winners)}"
        return f"Round {round_id} already drawn or not found."
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@shared_task
def auto_create_rounds():
    """
    Periodic task — jab koi open round na ho toh automatically banao.
    django-celery-beat se schedule karo (every 5 min).
    """
    from .models import Round
    from .services import RoundService
    from core.game_engine import GameVariation

    variations = [v.value for v in GameVariation]

    for variation in variations:
        open_count = Round.objects.filter(
            variation=variation,
            status=Round.Status.BETTING_OPEN
        ).count()

        if open_count == 0:
            round_obj = RoundService.create_round(variation)

            # V5 Jackpot ke liye Celery task schedule karo
            if variation == 'V5':
                from datetime import timedelta
                eta = timezone.now() + timedelta(minutes=10)  # testing
                trigger_jackpot_draw.apply_async(
                    args=[str(round_obj.id)],
                    eta=eta
                )