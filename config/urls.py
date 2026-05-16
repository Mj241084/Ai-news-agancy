from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", core_views.sitemap_xml_view, name="sitemap"),
    path("staff/", include("apps.staffpanel.urls", namespace="staffpanel")),
    path("", include("apps.core.urls", namespace="core")),
    path("", include("apps.taxonomy.urls", namespace="taxonomy")),
    path("", include("apps.entities.urls", namespace="entities")),
    path("", include("apps.content.urls", namespace="content")),
    path("", include("apps.interactions.urls", namespace="interactions")),
    path("", include("apps.accounts.urls", namespace="accounts")),
    path("", include("apps.search.urls", namespace="search")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
