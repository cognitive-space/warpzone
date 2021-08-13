import json
import time

from django.core.cache import caches

from huey.contrib.djhuey import db_periodic_task, db_task
from huey import crontab

from kubernetes.client.exceptions import ApiException

from worlds.models import Job


@db_task()
def update_job_status(jid):
    job = Job.objects.filter(id=jid).first()
    if job:
        job.update_status(logs=True)


@db_periodic_task(crontab(minute='*'))
def init_job_checks():
    for jid in Job.objects.exclude(status__in=Job.STATUS_DONE).values_list('id', flat=True):
        update_job_status(jid)


@db_task(retries=30, retry_delay=30)
def watch_log(jid, pod):
    time.sleep(5)
    job = Job.objects.filter(id=jid).first()
    client = caches['default'].get_client('default')

    if job:
        for event in job.watch_pod(pod):
            msg = json.dumps({'type': 'log', 'data': event + '\n'})
            client.rpush(pod, msg)
