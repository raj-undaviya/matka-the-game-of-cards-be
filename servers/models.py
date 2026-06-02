from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
 
User = get_user_model()
 
 
class GameServer(models.Model):
 
    class Status(models.TextChoices):
        LAUNCHING   = "launching",   "Launching"
        WARMING     = "warming",     "Warming"
        HEALTHY     = "healthy",     "Healthy"
        DEGRADED    = "degraded",    "Degraded"
        STOPPING    = "stopping",    "Stopping"
        STOPPED     = "stopped",     "Stopped"
        TERMINATED  = "terminated",  "Terminated"
        FAILED      = "failed",      "Failed"
 
    class RiskProfile(models.TextChoices):
        LOW    = "LOW",    "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH   = "HIGH",   "High"
 
    class Region(models.TextChoices):
        US_EAST_1    = "us-east-1",    "US East (N. Virginia)"
        EU_CENTRAL_1 = "eu-central-1", "EU Central (Frankfurt)"
        AP_SOUTH_1   = "ap-south-1",   "AP South (Mumbai)"
 
    # Admin panel ke fields — modal se directly map hote hain
    arena_name      = models.CharField(max_length=100, unique=True)
    region          = models.CharField(max_length=30, choices=Region.choices)
    max_players     = models.PositiveIntegerField(default=1000)
    risk_profile    = models.CharField(max_length=10, choices=RiskProfile.choices, default=RiskProfile.LOW)
    liquidity_seed  = models.DecimalField(max_digits=12, decimal_places=2, default=50000)
 
    # AWS se milne wali info
    instance_id     = models.CharField(max_length=30, blank=True, null=True)
    instance_type   = models.CharField(max_length=20, blank=True)
    public_ip       = models.GenericIPAddressField(blank=True, null=True)
    private_ip      = models.GenericIPAddressField(blank=True, null=True)
 
    # Status tracking
    status          = models.CharField(max_length=20, choices=Status.choices, default=Status.LAUNCHING)
    latency_ms      = models.IntegerField(default=0)
 
    # Audit
    created_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="servers_created")
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    terminated_at   = models.DateTimeField(blank=True, null=True)
 
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Game Server"
        verbose_name_plural = "Game Servers"
 
    def __str__(self):
        return f"{self.arena_name} ({self.region}) — {self.status}"
 
    @property
    def display_region(self):
        """US-EAST-1 format — image jaisa"""
        return self.region.upper()
 
    @property
    def is_active(self):
        return self.status in [self.Status.WARMING, self.Status.HEALTHY]
 