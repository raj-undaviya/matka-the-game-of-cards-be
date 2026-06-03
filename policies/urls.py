"""
Policies & Compliance — URL Configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ComplianceDashboardView,
    PolicyDocumentViewSet,
    PolicyVersionViewSet,
    JurisdictionViewSet,
    RestrictionControlViewSet,
    ExportReportView,
)

router = DefaultRouter()
router.register("documents",    PolicyDocumentViewSet,    basename="policy-document")
router.register("versions",     PolicyVersionViewSet,     basename="policy-version")
router.register("jurisdictions", JurisdictionViewSet,     basename="jurisdiction")
router.register("restrictions", RestrictionControlViewSet, basename="restriction")

urlpatterns = [
    # Dashboard — ek call mein saara data
    path("dashboard/",  ComplianceDashboardView.as_view(), name="compliance-dashboard"),

    # Export Report button
    path("export/",     ExportReportView.as_view(),        name="compliance-export"),

    # Router-generated CRUD routes
    path("", include(router.urls)),
]
