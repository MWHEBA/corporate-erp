from django.urls import path
from . import views
from . import views_pricing
from . import api_views
from .views_settings.supplier_type_settings_views import *

app_name = "supplier"

urlpatterns = [
    path("", views.supplier_list, name="supplier_list"),
    path("add/", views.supplier_add, name="supplier_add"),
    path("create/", views.supplier_add, name="supplier_create"),  # Alias for consistency
    path("create/modal/", views.supplier_create_modal, name="supplier_create_modal"),
    path("<int:pk>/edit/", views.supplier_edit, name="supplier_edit"),
    path("<int:pk>/delete/", views.supplier_delete, name="supplier_delete"),
    path("<int:pk>/detail/", views.supplier_detail, name="supplier_detail"),
    path(
        "<int:pk>/change-account/",
        views.supplier_change_account,
        name="supplier_change_account",
    ),
    path(
        "<int:pk>/create-account/",
        views.supplier_create_account,
        name="supplier_create_account",
    ),
    # Note: Specialized services URLs have been removed as part of supplier categories cleanup
    # Note: API URLs for specialized services have been removed as part of supplier categories cleanup
    # Note: Price comparison and calculator URLs have been removed as part of supplier categories cleanup
    # API endpoints
    path("api/list/", views.supplier_list_api, name="supplier_list_api"),
    path("api/supplier-types-styles/", api_views.supplier_types_styles_api, name="supplier_types_styles_api"),
    # Note: Paper and service-related API endpoints have been removed as part of supplier categories cleanup
    
    # إعدادات أنواع الموردين الديناميكية
    path(
        "settings/types/",
        supplier_type_settings_list,
        name="supplier_type_settings_list",
    ),
    path(
        "settings/types/create/",
        supplier_type_settings_create,
        name="supplier_type_settings_create",
    ),
    path(
        "settings/types/<int:pk>/edit/",
        supplier_type_settings_edit,
        name="supplier_type_settings_edit",
    ),
    path(
        "settings/types/<int:pk>/delete/",
        supplier_type_settings_delete,
        name="supplier_type_settings_delete",
    ),
    path(
        "settings/types/<int:pk>/preview/",
        supplier_type_settings_preview,
        name="supplier_type_settings_preview",
    ),
    path(
        "settings/types/<int:pk>/toggle-status/",
        supplier_type_settings_toggle_status,
        name="supplier_type_settings_toggle_status",
    ),
    path(
        "settings/types/reorder/",
        supplier_type_settings_reorder,
        name="supplier_type_settings_reorder",
    ),
    path(
        "settings/types/bulk-action/",
        supplier_type_settings_bulk_action,
        name="supplier_type_settings_bulk_action",
    ),
    path(
        "settings/types/export/",
        supplier_type_settings_export,
        name="supplier_type_settings_export",
    ),
    path(
        "settings/types/sync/",
        supplier_type_settings_sync,
        name="supplier_type_settings_sync",
    ),
]
