from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from ops_kit import views as ops_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('design-studio/', include('design_studio.urls')),
    path('ops/', include('ops_kit.urls')),
    path('healthz', ops_views.healthz_view, name='healthz'),
    path('healthz/', ops_views.healthz_view, name='healthz_slash'),
]

try:
    from ops_kit.runtime import get_runtime_urlpatterns, optional_kit_path
    urlpatterns += optional_kit_path('domain_kit', 'domain/', 'domain_kit.urls')
    urlpatterns += optional_kit_path('cal_kit', 'calendar/', 'cal_kit.urls')
    urlpatterns += optional_kit_path('notify_kit', 'notifications/', 'notify_kit.urls')
    urlpatterns += get_runtime_urlpatterns(settings.BASE_DIR, urlpatterns)
except ImportError:
    urlpatterns += [
        path('domain/', include('domain_kit.urls')),
        path('calendar/', include('cal_kit.urls')),
    ]

urlpatterns += [
    path('', include('pwa.urls')),
    path('', include('core.urls')),
    # Media-Dateien IMMER ausliefern (auch bei DEBUG=False im Gunicorn-Produktionsbetrieb)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

handler404 = 'core.views.custom_404_view'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
