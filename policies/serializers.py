"""
Policies & Compliance — Serializers
"""

from rest_framework import serializers
from .models import PolicyDocument, PolicyVersion, Jurisdiction, RestrictionControl


# ── PolicyVersion ──────────────────────────────────────────────────────────────

class PolicyVersionSerializer(serializers.ModelSerializer):
    updated_by_name   = serializers.SerializerMethodField()
    updated_by_initials = serializers.SerializerMethodField()
    document_name     = serializers.CharField(source="document.get_doc_type_display", read_only=True)

    class Meta:
        model  = PolicyVersion
        fields = [
            "id", "version_number", "document", "document_name",
            "change_summary", "updated_by", "updated_by_name",
            "updated_by_initials", "created_at", "content",
        ]
        read_only_fields = ["id", "created_at", "document_name", "updated_by_name", "updated_by_initials"]

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return "System"

    def get_updated_by_initials(self, obj):
        if obj.updated_by:
            name = obj.updated_by.get_full_name()
            if name:
                parts = name.split()
                return "".join(p[0].upper() for p in parts[:2])
            return obj.updated_by.username[:2].upper()
        return "SY"


# ── PolicyDocument ─────────────────────────────────────────────────────────────

class PolicyDocumentListSerializer(serializers.ModelSerializer):
    """Lightweight — list / tab switching ke liye"""
    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)
    latest_version   = serializers.SerializerMethodField()

    class Meta:
        model  = PolicyDocument
        fields = [
            "id", "doc_type", "doc_type_display", "title",
            "is_published", "published_at", "latest_version",
            "created_at", "updated_at",
        ]

    def get_latest_version(self, obj):
        v = obj.versions.first()
        if v:
            return {"version_number": v.version_number, "created_at": v.created_at}
        return None


class PolicyDocumentDetailSerializer(serializers.ModelSerializer):
    """Full content + recent versions — editor view ke liye"""
    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)
    versions         = PolicyVersionSerializer(many=True, read_only=True)

    class Meta:
        model  = PolicyDocument
        fields = [
            "id", "doc_type", "doc_type_display", "title", "content",
            "is_published", "published_at", "versions",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_published", "published_at", "created_at", "updated_at", "versions"]


class PolicyDocumentUpdateSerializer(serializers.ModelSerializer):
    """PATCH — editor se content save karne ke liye (Save Changes button)"""

    class Meta:
        model  = PolicyDocument
        fields = ["title", "content"]


class PublishSerializer(serializers.Serializer):
    """POST /publish/ — Publish Changes button"""
    change_summary = serializers.CharField(max_length=500, required=False, default="")


# ── Jurisdiction ───────────────────────────────────────────────────────────────

class JurisdictionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model  = Jurisdiction
        fields = [
            "id", "code", "name", "description",
            "status", "status_display", "compliance_score",
            "is_active", "notes", "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class JurisdictionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Jurisdiction
        fields = ["status", "compliance_score", "notes", "is_active"]


# ── RestrictionControl ─────────────────────────────────────────────────────────

class RestrictionControlSerializer(serializers.ModelSerializer):
    last_toggled_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = RestrictionControl
        fields = [
            "id", "name", "description", "slug",
            "is_enabled", "last_toggled_by_name", "last_toggled_at", "order",
        ]
        read_only_fields = ["id", "slug", "last_toggled_by_name", "last_toggled_at"]

    def get_last_toggled_by_name(self, obj):
        if obj.last_toggled_by:
            return obj.last_toggled_by.get_full_name() or obj.last_toggled_by.username
        return None


# ── Dashboard / Export ────────────────────────────────────────────────────────

class ComplianceDashboardSerializer(serializers.Serializer):
    """
    GET /dashboard/ — ek call mein saara data
    Left panel + tabs metadata ke liye
    """
    overall_compliance_score = serializers.IntegerField()
    jurisdictions            = JurisdictionSerializer(many=True)
    restriction_controls     = RestrictionControlSerializer(many=True)
    documents                = PolicyDocumentListSerializer(many=True)