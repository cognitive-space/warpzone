import datetime
import json
import time

from django.core.cache import caches
from django.core.files.base import ContentFile
from django.utils import timezone

from huey.contrib.djhuey import db_periodic_task, db_task
from huey import crontab

from loguru import logger
from kubernetes.client.exceptions import ApiException

from worlds.models import INTEGRATIONS, Job, Pipeline, StreamLog


@db_task()
def update_job_status(jid):
    job = Job.objects.filter(id=jid).first()
    if job:
        if job.status in job.STATUS_DONE:
            return

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


@db_task(retries=60, retry_delay=10)
def watch_log(jid, pod):
    time.sleep(5)
    job = Job.objects.filter(id=jid).first()
    client = caches['default'].get_client('default')

    if job:
        if job.status in job.STATUS_DONE:
            return

        logger.info('Starting log watch: {} {}', job, pod)
        log = StreamLog.objects.filter(job=job, pod=pod).first()
        if not log:
            log = StreamLog(job=job, pod=pod)

        if not log.log_file:
            log.lines = 0
            log.log_file.save(f'{pod}.log', content=ContentFile(b''), save=False)

        log.save()

        buffer = {}
        buffer_time = time.time()
        with log.log_file.open('a') as fh:
            for event in job.watch_pod(pod):
                fh.write(event + '\n')
                buffer[f'{pod}-{log.lines}'] = event + '\n'
                log.lines += 1

                if len(buffer) > 32 or (time.time() - buffer_time) > 3:
                    caches['default'].set_many(buffer, 180)
                    log.save()

                    buffer = {}
                    buffer_time = time.time()

            if buffer:
                caches['default'].set_many(buffer, 180)
                log.save()

            if log.lines:
                log.status = 'completed'
                log.save()
                logger.info('Completed log watch: {} {}', job, pod)

            else:
                if log.retries < 15:
                    log.retries += 1
                    log.save()
                    watch_log.schedule((job.id, pod), delay=60)
                    logger.info('Retrying log watch: {} {}', job, pod)


                else:
                    log.status = 'failed'
                    log.save()


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
            logger.info('Queue Still Running: Pipeline: {}; Job: {}', pipeline.id, qjob.id)
            scale_down.schedule((pipeline.id,), delay=600)
            return

        for key, mod in INTEGRATIONS.items():
            if key in pipeline.force_scaling:
                return mod.scale_down(pipeline, pipeline.force_scaling[key])


@db_periodic_task(crontab(hour='*/4', minute="0"))
def cleanup():
    old = timezone.now() - datetime.timedelta(hours=24)
    qs = StreamLog.objects.filter(modified__lt=old)
    cnt = qs.count()
    qs.delete()
    logger.info('Deleted StreamLogs: {}', cnt)

    old = timezone.now() - datetime.timedelta(days=7)
    qs = Job.objects.filter(modified__lt=old)
    cnt = qs.count()
    qs.delete()
    logger.info('Deleted Jobs: {}', cnt)
