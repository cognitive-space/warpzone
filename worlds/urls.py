from django.urls import path

from worlds.views import *

urlpatterns = [
    path('job/start/', start_job),
    path('pipeline/start/', start_pipeline),
    path('pipelines/', pipeline_list),
    path('jobs/', job_list),
    path('job/<int:jid>/', job_details),
    path('job/<int:jid>/kill/', job_kill),
    path('job/<int:jid>/<str:pod>.log', job_log),
    path('job/<int:jid>/<str:zip>.logs.zip', all_logs),
    path('job/<int:jid>/<str:zip>.zip', job_zip),
]
