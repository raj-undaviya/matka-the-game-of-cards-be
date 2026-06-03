"""
Policies & Compliance — Django Admin
"""

from django.contrib import admin
from .models import PolicyDocument, PolicyVersion, Jurisdiction, RestrictionControl


class PolicyVersionInline(admin.TabularInline):
    model         = PolicyVersion
    extra         = 0
    readonly_fields = ["version_number", "updated_by", "change_summary", "created_at"]
    fields        = ["version_number", "updated_by", "change_summary", "created_at"]
    can_delete    = False
    max_num       = 0  # Inline sirf read-only history ke liye


@admin.register(PolicyDocument)
class PolicyDocumentAdmin(admin.ModelAdmin):
    list_display   = ["doc_type", "title", "is_published", "published_at", "updated_at"]
    list_filter    = ["is_published", "doc_type"]
    search_fields  = ["title", "content"]
    readonly_fields = ["is_published", "published_at", "created_at", "updated_at"]
    inlines        = [PolicyVersionInline]

    fieldsets = (
        ("Document Info", {
            "fields": ("doc_type", "title", "content")
        }),
        ("Status", {
            "fields": ("is_published", "published_at", "created_at", "updated_at"),
        }),
    )


@admin.register(PolicyVersion)
class PolicyVersionAdmin(admin.ModelAdmin):
    list_display   = ["version_number", "document", "updated_by", "change_summary", "created_at"]
    list_filter    = ["document__doc_type"]
    search_fields  = ["version_number", "change_summary"]
    readonly_fields = ["created_at"]

    def has_add_permission(self, request):
        return False  # Versions sirf publish action se bante hain


@admin.register(Jurisdiction)
class JurisdictionAdmin(admin.ModelAdmin):
    list_display  = ["code", "name", "status", "compliance_score", "is_active", "updated_at"]
    list_filter   = ["status", "is_active"]
    search_fields = ["code", "name"]


@admin.register(RestrictionControl)
class RestrictionControlAdmin(admin.ModelAdmin):
    list_display  = ["name", "slug", "is_enabled", "last_toggled_by", "last_toggled_at", "order"]
    list_filter   = ["is_enabled"]
    readonly_fields = ["last_toggled_by", "last_toggled_at"]
    ordering      = ["order"]