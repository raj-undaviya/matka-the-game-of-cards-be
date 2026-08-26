from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
# Create your models here.

class User(AbstractUser):

    # ROLE_CHOICES = (
    #     ('admin', 'Admin'),
    #     ('customer', 'Customer'),
    #     ('dealer', 'Dealer'),
    #     ('distributor', 'Distributor'),
    # )

    Phone_number = models.CharField(max_length=15, blank=True, null=True)
    token = models.CharField(max_length=255, blank=True, null=True)
    # role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')

    # Dealer / Distributor ke liye
    # company_name = models.CharField(max_length=255, blank=True, null=True)
    # gst_number = models.CharField(max_length=15, blank=True, null=True)

    # Email verify status
    is_email_verified = models.BooleanField(default=False) 

    # Terms & Conditions acceptance details
    terms_accepted = models.BooleanField(default=False)
    terms_accepted_version = models.CharField(max_length=50, blank=True, null=True)
    terms_accepted_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.username} - {self.email}"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        # OTP expires after 10 minutes
        return (timezone.now() - self.created_at).seconds > 600    