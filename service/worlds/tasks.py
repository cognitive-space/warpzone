from huey.contrib.djhuey import db_periodic_task, db_task
from huey import crontab

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
