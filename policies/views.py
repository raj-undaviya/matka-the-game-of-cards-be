"""
Policies & Compliance — Views
=================================
Screen ke har action ke liye ek endpoint:

  GET  /api/policies/dashboard/              → Left panel + tabs data ek saath
  GET  /api/policies/documents/              → Saare documents (tab list)
  GET  /api/policies/documents/<id>/         → Single doc with content + versions
  PATCH /api/policies/documents/<id>/        → Save Changes (editor)
  POST /api/policies/documents/<id>/publish/ → Publish Changes button
  POST /api/policies/documents/<id>/save-draft/ → Auto-save

  GET  /api/policies/versions/               → Version history table (paginated)
  GET  /api/policies/versions/<id>/          → Single version detail
  DELETE /api/policies/versions/<id>/        → Delete version (trash icon)

  GET   /api/policies/jurisdictions/         → All jurisdictions
  PATCH /api/policies/jurisdictions/<id>/    → Update compliance status

  GET  /api/policies/restrictions/           → All toggles
  POST /api/policies/restrictions/<id>/toggle/ → Toggle on/off

  GET  /api/policies/export/                 → Export Report (PDF/JSON)
"""

import csv
import json
from datetime import datetime
from io import StringIO

from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Avg

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.pagination import PageNumberPagination

from .models import PolicyDocument, PolicyVersion, Jurisdiction, RestrictionControl
from .serializers import (
    PolicyDocumentListSerializer,
    PolicyDocumentDetailSerializer,
    PolicyDocumentUpdateSerializer,
    PublishSerializer,
    PolicyVersionSerializer,
    JurisdictionSerializer,
    JurisdictionUpdateSerializer,
    RestrictionControlSerializer,
    ComplianceDashboardSerializer,
)


# ── Pagination ─────────────────────────────────────────────────────────────────

class VersionPagination(PageNumberPagination):
    page_size            = 10   # Screen pe ~4 rows dikhte hain, 10 per page rakhte hain
    page_size_query_param = "page_size"
    max_page_size        = 50


# ── Dashboard — ek call mein saara left panel data ─────────────────────────────

class ComplianceDashboardView(APIView):
    """
    GET /api/policies/dashboard/

    Admin panel open hote hi yeh call hogi.
    Left panel + tab headers ka saara data deta hai.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        jurisdictions     = Jurisdiction.objects.filter(is_active=True)
        restrictions      = RestrictionControl.objects.all()
        documents         = PolicyDocument.objects.all()

        # Overall compliance = average of all jurisdiction scores
        avg = jurisdictions.aggregate(avg=Avg("compliance_score"))["avg"] or 0
        overall_score = round(avg)

        data = {
            "overall_compliance_score": overall_score,
            "jurisdictions":            jurisdictions,
            "restriction_controls":     restrictions,
            "documents":                documents,
        }
        serializer = ComplianceDashboardSerializer(data)
        return Response(serializer.data)


# ── PolicyDocument CRUD ────────────────────────────────────────────────────────

class PolicyDocumentViewSet(ModelViewSet):
    """
    GET    /api/policies/documents/        → list (tab headers)
    GET    /api/policies/documents/<id>/   → detail with content + versions
    PATCH  /api/policies/documents/<id>/   → Save Changes (editor auto-save)
    POST   /api/policies/documents/<id>/publish/    → Publish Changes button
    POST   /api/policies/documents/<id>/save-draft/ → Save as draft
    """
    permission_classes = [IsAdminUser]
    http_method_names  = ["get", "patch", "post", "head", "options"]  # DELETE allowed only on versions

    def get_queryset(self):
        return PolicyDocument.objects.prefetch_related("versions__updated_by").all()

    def get_serializer_class(self):
        if self.action == "list":
            return PolicyDocumentListSerializer
        if self.action in ["partial_update", "update"]:
            return PolicyDocumentUpdateSerializer
        return PolicyDocumentDetailSerializer

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH /api/policies/documents/<id>/
        Editor ka "Save Changes" button — sirf content update
        """
        instance   = self.get_object()
        serializer = PolicyDocumentUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message":    "Draft saved successfully.",
            "updated_at": instance.updated_at,
            "doc_type":   instance.doc_type,
        })

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        """
        POST /api/policies/documents/<id>/publish/
        Body: { "change_summary": "Updated clause 2.4 for UKGC compliance" }

        Screen ka bada green "Publish Changes" button
        """
        document   = self.get_object()
        serializer = PublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        version = document.publish(
            published_by   = request.user,
            change_summary = serializer.validated_data["change_summary"],
        )

        return Response({
            "message":        f"{document.get_doc_type_display()} published successfully.",
            "version_number": version.version_number,
            "published_at":   document.published_at,
            "version_id":     version.id,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="save-draft")
    def save_draft(self, request, pk=None):
        """
        POST /api/policies/documents/<id>/save-draft/
        Auto-save draft without publishing.
        Last saved: 12m ago — yeh timestamp update karta hai
        """
        document = self.get_object()
        if "content" in request.data:
            document.content = request.data["content"]
        if "title" in request.data:
            document.title = request.data["title"]
        document.save(update_fields=["content", "title", "updated_at"])

        return Response({
            "message":    "Draft auto-saved.",
            "updated_at": document.updated_at,
        })


# ── PolicyVersion ──────────────────────────────────────────────────────────────

class PolicyVersionViewSet(ModelViewSet):
    """
    GET    /api/policies/versions/       → Version history table (paginated)
    GET    /api/policies/versions/<id>/  → Single version (eye icon → view)
    DELETE /api/policies/versions/<id>/  → Delete (trash icon)

    Query params:
      ?document=<doc_id>   → filter by document
      ?doc_type=terms_of_service|privacy_policy|responsible_gaming
    """
    permission_classes  = [IsAdminUser]
    serializer_class    = PolicyVersionSerializer
    pagination_class    = VersionPagination
    http_method_names   = ["get", "delete", "head", "options"]

    def get_queryset(self):
        qs = PolicyVersion.objects.select_related("document", "updated_by").all()

        doc_id   = self.request.query_params.get("document")
        doc_type = self.request.query_params.get("doc_type")

        if doc_id:
            qs = qs.filter(document_id=doc_id)
        if doc_type:
            qs = qs.filter(document__doc_type=doc_type)

        return qs

    def destroy(self, request, *args, **kwargs):
        """
        DELETE /api/policies/versions/<id>/
        Version history ka trash icon
        """
        instance = self.get_object()

        # Latest (published) version delete nahi hone dena
        is_latest = not PolicyVersion.objects.filter(
            document=instance.document,
            created_at__gt=instance.created_at
        ).exists()

        if is_latest and instance.document.is_published:
            return Response(
                {"error": "Cannot delete the latest published version."},
                status=status.HTTP_400_BAD_REQUEST
            )

        instance.delete()
        return Response({"message": "Version deleted."}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        """
        POST /api/policies/versions/<id>/restore/
        Pencil icon → restore to this version
        """
        version  = self.get_object()
        document = version.document
        document.content = version.content
        document.save(update_fields=["content", "updated_at"])

        return Response({
            "message":        f"Document restored to {version.version_number}.",
            "version_number": version.version_number,
            "doc_type":       document.doc_type,
        })


# ── Jurisdiction ───────────────────────────────────────────────────────────────

class JurisdictionViewSet(ModelViewSet):
    """
    GET   /api/policies/jurisdictions/       → EU, GB, US list
    PATCH /api/policies/jurisdictions/<id>/  → Update compliance status / score
    """
    permission_classes = [IsAdminUser]
    http_method_names  = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return Jurisdiction.objects.all()

    def get_serializer_class(self):
        if self.action == "partial_update":
            return JurisdictionUpdateSerializer
        return JurisdictionSerializer

    def partial_update(self, request, *args, **kwargs):
        instance   = self.get_object()
        serializer = JurisdictionUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": f"{instance.name} compliance updated.",
            "code":    instance.code,
            "status":  instance.status,
            "score":   instance.compliance_score,
        })


# ── RestrictionControl ─────────────────────────────────────────────────────────

class RestrictionControlViewSet(ModelViewSet):
    """
    GET  /api/policies/restrictions/              → All toggles
    POST /api/policies/restrictions/<id>/toggle/  → ON/OFF toggle
    """
    permission_classes = [IsAdminUser]
    serializer_class   = RestrictionControlSerializer
    http_method_names  = ["get", "post", "head", "options"]

    def get_queryset(self):
        return RestrictionControl.objects.all()

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle(self, request, pk=None):
        """
        POST /api/policies/restrictions/<id>/toggle/
        Screen ke green/grey toggle switches
        """
        control     = self.get_object()
        new_state   = control.toggle(toggled_by=request.user)

        return Response({
            "id":         control.id,
            "name":       control.name,
            "slug":       control.slug,
            "is_enabled": new_state,
            "message":    f"'{control.name}' {'enabled' if new_state else 'disabled'} successfully.",
        })


# ── Export Report ──────────────────────────────────────────────────────────────

class ExportReportView(APIView):
    """
    GET /api/policies/export/?format=csv|json

    Screen ka "Export Report" button
    Default: JSON
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        export_format = request.query_params.get("format", "json").lower()

        # Saara data collect karo
        jurisdictions = Jurisdiction.objects.all()
        restrictions  = RestrictionControl.objects.all()
        versions      = PolicyVersion.objects.select_related("document", "updated_by").all()[:50]

        avg = jurisdictions.aggregate(avg=Avg("compliance_score"))["avg"] or 0

        report_data = {
            "generated_at":           timezone.now().isoformat(),
            "generated_by":           request.user.get_full_name() or request.user.username,
            "overall_compliance":     f"{round(avg)}%",
            "jurisdictions": [
                {
                    "code":   j.code,
                    "name":   j.name,
                    "status": j.status,
                    "score":  j.compliance_score,
                }
                for j in jurisdictions
            ],
            "restriction_controls": [
                {
                    "name":       r.name,
                    "slug":       r.slug,
                    "is_enabled": r.is_enabled,
                }
                for r in restrictions
            ],
            "policy_versions": [
                {
                    "version":         v.version_number,
                    "document":        v.document.get_doc_type_display(),
                    "updated_by":      v.updated_by.get_full_name() if v.updated_by else "System",
                    "date":            v.created_at.strftime("%b %d, %Y"),
                    "change_summary":  v.change_summary,
                }
                for v in versions
            ],
        }

        if export_format == "csv":
            return self._csv_response(report_data)
        return self._json_response(report_data)

    def _json_response(self, data):
        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type="application/json"
        )
        filename = f"compliance_report_{datetime.now().strftime('%Y%m%d')}.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _csv_response(self, data):
        output   = StringIO()
        writer   = csv.writer(output)

        writer.writerow(["COMPLIANCE REPORT"])
        writer.writerow(["Generated At", data["generated_at"]])
        writer.writerow(["Generated By", data["generated_by"]])
        writer.writerow(["Overall Compliance", data["overall_compliance"]])
        writer.writerow([])

        writer.writerow(["JURISDICTIONS"])
        writer.writerow(["Code", "Name", "Status", "Score"])
        for j in data["jurisdictions"]:
            writer.writerow([j["code"], j["name"], j["status"], j["score"]])
        writer.writerow([])

        writer.writerow(["POLICY VERSION HISTORY"])
        writer.writerow(["Version", "Document", "Updated By", "Date", "Change Summary"])
        for v in data["policy_versions"]:
            writer.writerow([v["version"], v["document"], v["updated_by"], v["date"], v["change_summary"]])

        response = HttpResponse(output.getvalue(), content_type="text/csv")
        filename = f"compliance_report_{datetime.now().strftime('%Y%m%d')}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response