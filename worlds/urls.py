from django.urls import path

from worlds.views import *

urlpatterns = [
    path('job/start/', start_job),
    path('job/<int:jid>/', job_details),
]
