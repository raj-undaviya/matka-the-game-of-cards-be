# policies/management/commands/seed_policies.py
# 
# Run: python manage.py seed_policies
#
# Yeh command screen mein dikhne wala initial data seed karega:
#   - 3 Policy Documents (Terms / Privacy / Responsible Gaming)
#   - 3 Jurisdictions (EU, GB, US)
#   - 3 Restriction Controls (Age / VPN / Self-Exclusion)

from django.core.management.base import BaseCommand
from policies.models import PolicyDocument, Jurisdiction, RestrictionControl


class Command(BaseCommand):
    help = "Seed initial Policies & Compliance data"

    def handle(self, *args, **kwargs):
        self._seed_documents()
        self._seed_jurisdictions() 
        self._seed_restrictions()
        self.stdout.write(self.style.SUCCESS("✅ Policies data seeded successfully!"))

    def _seed_documents(self):
        docs = [
            {
                "doc_type": PolicyDocument.DocType.TERMS_OF_SERVICE,
                "title":    "General Terms and Conditions",
                "content":  """<h1>General Terms and Conditions</h1>
<p>Welcome to our gaming platform. By accessing or using our services, you agree to be bound by these Terms and Conditions.</p>
<h2>1. Eligibility</h2>
<p>You must be at least 18 years of age (or the minimum legal age in your jurisdiction) to use our platform. We reserve the right to request proof of age and identity at any time.</p>
<h2>2. Account Registration</h2>
<p>Each user may maintain only one account. Providing false information during registration may result in account suspension and forfeiture of funds in accordance with applicable regulations.</p>
<h2>3. Responsible Gaming</h2>
<p>We provide deposit limits, session reminders, and self-exclusion tools. Players experiencing difficulties should contact our support team.</p>""",
            },
            {
                "doc_type": PolicyDocument.DocType.PRIVACY_POLICY,
                "title":    "Privacy Policy",
                "content":  """<h1>Privacy Policy</h1>
<p>This Privacy Policy explains how we collect, use, and protect your personal information.</p>
<h2>1. Data Collection</h2>
<p>We collect information you provide during registration, including name, email, and payment details.</p>
<h2>2. Data Usage</h2>
<p>Your data is used to provide services, process payments, and comply with regulatory requirements.</p>
<h2>3. Data Retention</h2>
<p>We retain your data for the period required by applicable law, typically 5 years post-account closure.</p>""",
            },
            {
                "doc_type": PolicyDocument.DocType.RESPONSIBLE_GAMING,
                "title":    "Responsible Gaming Policy",
                "content":  """<h1>Responsible Gaming Policy</h1>
<p>We are committed to providing a safe and responsible gaming environment.</p>
<h2>1. Deposit Limits</h2>
<p>Players may set daily, weekly, or monthly deposit limits at any time.</p>
<h2>2. Self-Exclusion</h2>
<p>Players can self-exclude for periods of 6 months, 1 year, 5 years, or permanently.</p>
<h2>3. Reality Checks</h2>
<p>Session reminders are sent at 30-minute intervals to help players track their activity.</p>""",
            },
        ]
        for d in docs:
            PolicyDocument.objects.get_or_create(doc_type=d["doc_type"], defaults=d)
        self.stdout.write("  → Policy documents seeded")

    def _seed_jurisdictions(self):
        jurisdictions = [
            {
                "code":             "EU",
                "name":             "European Union (GDPR)",
                "description":      "Data Privacy & Portability",
                "status":           "compliant",
                "compliance_score": 95,
            },
            {
                "code":             "GB",
                "name":             "United Kingdom (UKGC)",
                "description":      "Gambling Commission Standards",
                "status":           "compliant",
                "compliance_score": 88,
            },
            {
                "code":             "US",
                "name":             "United States (NJ DGE)",
                "description":      "Division of Gaming Enforcement",
                "status":           "partial",
                "compliance_score": 72,
            },
        ]
        for j in jurisdictions:
            Jurisdiction.objects.get_or_create(code=j["code"], defaults=j)
        self.stdout.write("  → Jurisdictions seeded")

    def _seed_restrictions(self):
        controls = [
            {
                "name":        "Mandatory Age Verification",
                "description": "Require ID check before first deposit",
                "slug":        "age_verification",
                "is_enabled":  True,
                "order":       1,
            },
            {
                "name":        "VPN Block Enforcement",
                "description": "Block anonymized proxy connections",
                "slug":        "vpn_block",
                "is_enabled":  True,
                "order":       2,
            },
            {
                "name":        "Self-Exclusion Global Sync",
                "description": "Sync exclusion lists across jurisdictions",
                "slug":        "self_exclusion_sync",
                "is_enabled":  False,
                "order":       3,
            },
        ]
        for c in controls:
            RestrictionControl.objects.get_or_create(slug=c["slug"], defaults=c)
        self.stdout.write("  → Restriction controls seeded")