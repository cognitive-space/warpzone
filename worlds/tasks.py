import json
import time

from django.core.cache import caches

from huey.contrib.djhuey import db_periodic_task, db_task
from huey import crontab

from loguru import logger
from kubernetes.client.exceptions import ApiException

from worlds.models import INTEGRATIONS, Job, Pipeline, StreamLog


@db_task()
def update_job_status(jid):
    job = Job.objects.filter(id=jid).first()
    if job:
        try:
            job.update_status(logs=True)

        except ApiException as exc:
            if exc.status == 400:
                if 'ContainerCreating' in json.loads(exc.body.decode())['message']:
                    job.status = 'downloading'
                    job.save()
                    return

            raise


@db_periodic_task(crontab(minute='*'))
def init_job_checks_launcher():
    init_job_checks()
    init_job_checks.schedule(delay=20)
    init_job_checks.schedule(delay=40)


@db_task()
def init_job_checks():
    for jid in Job.objects.exclude(status__in=Job.STATUS_DONE).values_list('id', flat=True):
        update_job_status(jid)


@db_task(retries=20, retry_delay=30)
def watch_log(jid, pod):
    time.sleep(5)
    job = Job.objects.filter(id=jid).first()
    client = caches['default'].get_client('default')

    if job:
        logger.info('Starting log watch: {} {}', job, pod)
        log = StreamLog.objects.filter(job=job, pod=pod).first()
        if not log:
            log = StreamLog(job=job, pod=pod)

        for event in job.watch_pod(pod):
            if log.logs:
                log.lines = len(log.logs.split('\n'))

            else:
                log.lines = 0
                log.logs = ''

            log.logs += event + '\n'
            log.lines += 1
            log.save()

        log.status = 'completed'
        log.save()
        logger.info('Completed log watch: {} {}', job, pod)


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
