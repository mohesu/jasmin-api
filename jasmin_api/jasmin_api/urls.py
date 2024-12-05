from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from django.views import static
from rest_framework.routers import DefaultRouter

# Import your viewsets
from rest_api.views import (
    GroupViewSet,
    UserViewSet,
    MORouterViewSet,
    SMPPCCMViewSet,
    HTTPCCMViewSet,
    MTRouterViewSet,
    FiltersViewSet,
)

# Import drf-yasg for Swagger documentation
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

# Initialize the router and register viewsets
router = DefaultRouter()
router.register(r'groups', GroupViewSet, basename='groups')
router.register(r'users', UserViewSet, basename='users')
router.register(r'morouters', MORouterViewSet, basename='morouters')
router.register(r'mtrouters', MTRouterViewSet, basename='mtrouters')
router.register(r'smppsconns', SMPPCCMViewSet, basename='smppcons')
router.register(r'httpsconns', HTTPCCMViewSet, basename='httpcons')
router.register(r'filters', FiltersViewSet, basename='filters')

# Setup drf-yasg schema view
schema_view = get_schema_view(
    openapi.Info(
        title="Jasmin Management REST API",
        default_version='v1',
        description="A REST API for managing Jasmin SMS Gateway",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),

    # API endpoints with versioning
    path('api/v1/', include((router.urls, 'api'), namespace='v1')),

    # Health check endpoint
    path('health/', include('health_check.urls')),

    # Swagger documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

# Serve static files only in development
if settings.DEBUG:
    urlpatterns += [
        path('static/<path:path>/', static.serve, {'document_root': settings.STATIC_ROOT}),
    ]
