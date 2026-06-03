"""
Policies & Compliance — Models
================================
Screen ke teeno sections cover karta hai:
  1. PolicyDocument     — Terms of Service / Privacy Policy / Responsible Gaming
  2. PolicyVersion      — Version history (v4.2.0, v4.1.2 …)
  3. Jurisdiction       — EU/GB/US compliance status
  4. RestrictionControl — Age Verification / VPN Block / Self-Exclusion toggles
"""

from django.db import models
from django.utils import timezone
from auths.models import User


class PolicyDocument(models.Model):
    """
    Screen ke 3 tabs:
      Terms of Service | Privacy Policy | Responsible Gaming
    """

    class DocType(models.TextChoices):
        TERMS_OF_SERVICE    = "terms_of_service",    "Terms of Service"
        PRIVACY_POLICY      = "privacy_policy",      "Privacy Policy"
        RESPONSIBLE_GAMING  = "responsible_gaming",  "Responsible Gaming"

    doc_type    = models.CharField(max_length=30, choices=DocType.choices, unique=True)
    title       = models.CharField(max_length=200)
    content     = models.TextField()               # Rich text / HTML
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Policy Document"
        verbose_name_plural = "Policy Documents"

    def __str__(self):
        return f"{self.get_doc_type_display()} ({'Published' if self.is_published else 'Draft'})"

    def publish(self, published_by: User, change_summary: str = ""):
        """
        'Publish Changes' button → yeh method call hoga.
        Auto version bump bhi karega.
        """
        # Latest version find karo
        latest = self.versions.order_by("-created_at").first()
        if latest:
            major, minor, patch = map(int, latest.version_number.lstrip("v").split("."))
            new_version = f"v{major}.{minor + 1}.0"
        else:
            new_version = "v1.0.0"

        # Naya version create karo
        version = PolicyVersion.objects.create(
            document       = self,
            version_number = new_version,
            content        = self.content,
            updated_by     = published_by,
            change_summary = change_summary or f"Published {self.get_doc_type_display()}",
        )

        self.is_published = True
        self.published_at = timezone.now()
        self.save()

        return version


class PolicyVersion(models.Model):
    """
    Version History table — screen ke bottom section.
    VERSION | DOCUMENT | UPDATED BY | DATE | CHANGE SUMMARY | ACTIONS
    """

    document        = models.ForeignKey(PolicyDocument, on_delete=models.CASCADE, related_name="versions")
    version_number  = models.CharField(max_length=20)   # "v4.2.0"
    content         = models.TextField()                 # Snapshot of content at this version
    updated_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="policy_versions")
    change_summary  = models.CharField(max_length=500)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["-created_at"]
        verbose_name        = "Policy Version"
        verbose_name_plural = "Policy Versions"

    def __str__(self):
        return f"{self.version_number} — {self.document.get_doc_type_display()}"


class Jurisdiction(models.Model):
    """
    Left panel — Jurisdictional Status:
      EU (GDPR) | GB (UKGC) | US (NJ DGE)
    """

    class ComplianceStatus(models.TextChoices):
        COMPLIANT     = "compliant",     "Compliant"
        PARTIAL       = "partial",       "Partial"
        NON_COMPLIANT = "non_compliant", "Non-Compliant"
        PENDING       = "pending",       "Pending Review"

    code            = models.CharField(max_length=10, unique=True)   # "EU", "GB", "US"
    name            = models.CharField(max_length=100)               # "European Union (GDPR)"
    description     = models.CharField(max_length=200)               # "Data Privacy & Portability"
    status          = models.CharField(max_length=20, choices=ComplianceStatus.choices, default=ComplianceStatus.PENDING)
    compliance_score = models.PositiveSmallIntegerField(default=0)   # 0-100 → "88% COMPLIANT"
    is_active       = models.BooleanField(default=True)
    notes           = models.TextField(blank=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ["code"]
        verbose_name        = "Jurisdiction"
        verbose_name_plural = "Jurisdictions"

    def __str__(self):
        return f"{self.code} — {self.name} ({self.status})"


class RestrictionControl(models.Model):
    """
    Left panel — Restriction Controls toggles:
      Mandatory Age Verification | VPN Block Enforcement | Self-Exclusion Global Sync
    """

    name            = models.CharField(max_length=100)    # "Mandatory Age Verification"
    description     = models.CharField(max_length=200)    # "Require ID check before first deposit"
    slug            = models.SlugField(unique=True)        # "age_verification"
    is_enabled      = models.BooleanField(default=False)
    last_toggled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    last_toggled_at = models.DateTimeField(null=True, blank=True)
    order           = models.PositiveSmallIntegerField(default=0)  # Display order

    class Meta:
        ordering            = ["order"]
        verbose_name        = "Restriction Control"
        verbose_name_plural = "Restriction Controls"

    def __str__(self):
        return f"{self.name} ({'ON' if self.is_enabled else 'OFF'})"

    def toggle(self, toggled_by: User):
        self.is_enabled      = not self.is_enabled
        self.last_toggled_by = toggled_by
        self.last_toggled_at = timezone.now()
        self.save()
        return self.is_enabled