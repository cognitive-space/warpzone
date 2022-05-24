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

from warpzone.shelix_api import StarHelixApi
from worlds.models import Job, Pipeline, StreamLog, Cluster, CompletedLog


@db_task()
def update_job_status(jid):
    job = Job.objects.filter(id=jid).first()
    if job:
        if job.status in job.STATUS_DONE:
            return

        try:
            job.update_status(logs=True)

        except ApiException as exc:
            msg = exc.body.decode()

            if exc.status == 400:
                if 'ContainerCreating' in json.loads(msg)['message']:
                    job.status = 'downloading'
                    job.save()
                    job.log('Waiting for container creation\n')

                else:
                    job.log(f'Error: {msg}\n')
                    raise

            else:
                job.log(f'Error: {msg}\n')
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

        log.lines = 0
        if not log.log_file:
            log.log_file.save(f'{pod}.log', content=ContentFile(b''), save=False)

        log.save()

        buffer = {}
        buffer_time = time.time()
        with log.log_file.open('w') as fh:
            for event in job.watch_pod(pod):
                fh.write(event + '\n')
                buffer[f'{pod}-{log.lines}'] = event + '\n'
                log.lines += 1

                if len(buffer) > 32 or (time.time() - buffer_time) > 3:
                    caches['default'].set_many(buffer, 180)
                    log.save()

                    if log.lines > 500000:
                        log.status = 'completed'
                        log.save()
                        logger.info('Line limit Exiting: {} {}', job, pod)
                        return

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


@db_task(retries=3, retry_delay=10)
def end_shelix_log(job_id):
    job = Job.objects.filter(id=job_id).first()
    content = ''
    after = None

    if job:
        while 1:
            text, lastchunk, endlog = StarHelixApi.read_log(job.shelix_log_id, after)
            if not endlog:
                end_shelix_log.schedule(delay=10, args=(job_id,))
                return

            if not text:
                break

            content += text
            if lastchunk:
                after = lastchunk

            time.sleep(0.1)

        content = content.encode()
        log = CompletedLog(job=job)
        log.log_file.save(f'{job.job_name}.completed.log', content=ContentFile(content), save=False)
        log.save()


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
