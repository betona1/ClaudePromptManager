from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('api/', include('core.urls_api')),
    path('api/federation/', include('core.urls_federation')),
    path('.well-known/cpm-federation', include('core.urls_federation_wellknown')),
    # Serve screenshots directly (bypasses WhiteNoise caching for dynamic uploads)
    re_path(r'^static/screenshots/(?P<path>.*)$', serve,
            {'document_root': settings.BASE_DIR / 'static' / 'screenshots'}),
    path('', include('core.urls_web')),
]
