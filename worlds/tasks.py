import json
import time

from django.core.cache import caches

from huey.contrib.djhuey import db_periodic_task, db_task
from huey import crontab

from loguru import logger
from kubernetes.client.exceptions import ApiException

from worlds.models import INTEGRATIONS, Job, Pipeline


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

            # todo: kill faster
            shutdown = caches['default'].get(f'shutdown-{pod}')
            if shutdown:
                caches['default'].delete(f'shutdown-{pod}')
                caches['default'].delete(pod)
                logger.info('Shutting Down Log Stream: {}', pod)
                return


@db_task(retries=10, retry_delay=60)
def scale_down(pipeline):
    pipeline = Pipeline.objects.filter(id=pipeline).first()
    if pipeline:
        qjob = Job.objects.filter(
            status__in=Job.STATUS_RUNNING,
            pipeline=pipeline,
            job_type='queue'
        ).first()

        if qjob:
            return

        for key, mod in INTEGRATIONS.items():
            if key in pipeline.force_scaling:
                return mod.scale_down(pipeline, pipeline.force_scaling[key])
