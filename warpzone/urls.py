"""warpzone URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.views.static import serve

import worlds.views as worlds_views


def trigger_error(request):
    division_by_zero = 1 / 0


urlpatterns = []

if settings.DEBUG :
    urlpatterns.append(path(
        'media/<path:path>',
        serve,
        {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}
    ))

urlpatterns += [
    path('admin/', admin.site.urls),
    path('worlds/', include('worlds.urls')),
    path('favicon.ico', worlds_views.favicon),
    # path('sentry-debug/', trigger_error),
    path('', worlds_views.start_job),
]
