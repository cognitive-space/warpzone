from django.urls import path

from worlds.views import *

urlpatterns = [
    path('job/start/', start_job),
    path('jobs/', job_list),
    path('job/<int:jid>/', job_details),
    path('job/<int:jid>/kill/', job_kill),
    path('job/<int:jid>/<str:pod>.log', job_log),
]
