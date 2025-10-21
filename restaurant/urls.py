from .views import *
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.views import defaults as default_views
from django.views.generic import TemplateView

urlpatterns = [
    path('sw.js', TemplateView.as_view(template_name='sw.js', content_type='application/javascript'), name='sw.js'),
    path('pos/', include('pos.urls', namespace='pos')),
    path("admin/", admin.site.urls),
    path('settings/', include('settings.urls', namespace='settings')),
    path('users/', include('users.urls', namespace='users')),
    path('analytics/', include('analytics.urls')),
    path('finance/', include('finance.urls', namespace='finance')),
    path('inventory/', include('inventory.urls', namespace='inventory')),
    path('production/', include('production.urls', namespace='production')),
    # path('__debug__/', include('debug_toolbar.urls')),

    #dash
    path('dashboard/', dashboard_view, name='dashborad'),
    path('api/dashboard-stats/', dashboard_stats_api, name='dashboard_stats_api'),
    path('api/chart-data/', chart_data_api, name='chart_data_api'),
    path('api/orders-list/', orders_list_api, name='orders_list_api')
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
