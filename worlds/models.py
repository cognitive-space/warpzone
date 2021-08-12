import io
import time

from django.db import models
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.postgres.fields import ArrayField

import yaml
from dotenv import dotenv_values
from loguru import logger
from fernet_fields import EncryptedTextField

from kubernetes import client as kube_apis
from kubernetes import watch as kube_watch
from kubernetes.client import ApiClient, Configuration
from kubernetes.client.exceptions import ApiException
from kubernetes.config.kube_config import _get_kube_config_loader


class Pipeline(models.Model):
    name = models.CharField(max_length=70)
    slug = models.SlugField(max_length=70, unique=True)

    worker_command = models.CharField(max_length=512)
    workers = models.PositiveSmallIntegerField()

    config = EncryptedTextField(help_text='kube config file', blank=True, null=True)
    envs = EncryptedTextField(help_text='use .env format', blank=True, null=True)

    def __str__(self):
        return self.name

    def to_json(self):
        return {
            'name': self.name,
            'id': self.id,
            'slug': self.slug,
        }

    def kube_client(self):
        client_config = type.__call__(Configuration)
        loader = _get_kube_config_loader(config_dict=yaml.load(self.config, Loader=yaml.SafeLoader))

        loader.load_and_set(client_config)
        return ApiClient(configuration=client_config)

    def run_job(self, image, job_command, wait=False):
        qjob = Job.objects.filter(
            image=image,
            status__in=Job.STATUS_RUNNING,
            pipeline=self,
            job_type='queue'
        ).first()

        if qjob is None:
            qjob = Job(
                command=self.worker_command.split(' '),
                image=image,
                parallelism=self.workers,
                pipeline=self,
                job_type='queue',
            )
            qjob.save()
            qjob.run()

        time.sleep(0.1)

        job = Job(
            command=job_command.split(' '),
            image=image,
            parallelism=1,
            pipeline=self,
            job_type='job',
            queue=qjob,
        )
        job.save()
        job.run()
        return qjob, job

    def env_list(self):
        ret = []
        if self.envs:
            stream = io.StringIO(self.envs)
            for name, value in dotenv_values(stream=stream).items():
                ret.append({'name': name, 'value': value})

        return ret


class Job(models.Model):
    STATUS = (
        ('created', 'Created'),
        ('submitted', 'Submitted'),
        ('active', 'Active'),
        ('killed', 'Killed'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
    )

    STATUS_RUNNING = ['active', 'created', 'submitted']
    STATUS_DONE = ['completed', 'killed', 'failed']

    JOB_TYPES = (
        ('queue', 'Queue'),
        ('job', 'Job'),
    )

    command = ArrayField(models.CharField(max_length=255))
    image = models.CharField(max_length=255)
    parallelism = models.PositiveSmallIntegerField(default=1)

    succeeded = models.PositiveSmallIntegerField(default=0)
    failed = models.PositiveSmallIntegerField(default=0)

    job_name = models.CharField(max_length=255, blank=True, null=True)
    job_definition = models.JSONField(blank=True, null=True, encoder=DjangoJSONEncoder)
    job_type = models.CharField(max_length=10, choices=JOB_TYPES)
    queue = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE)

    status = models.CharField(max_length=25, choices=STATUS, default='created')

    pods = ArrayField(models.CharField(max_length=255), blank=True, null=True)

    log_data = models.JSONField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created']

    @property
    def name(self):
        if self.job_name:
            return self.job_name

        return ' '.join(self.command)[:75]

    def __str__(self):
        return self.name

    def to_json(self):
        return {
            'job_name': self.job_name,
            'id': self.id,
            'status': self.status,
            'pipeline': self.pipeline.to_json(),
            'pods': self.pods,
            'log_data': self.complete_logs,
            'modified': self.modified.isoformat(),
            'created': self.created.isoformat()
        }

    @property
    def complete_logs(self):
        if self.status in self.STATUS_DONE:
            return self.log_data

        return {}

    def run(self, wait=False):
        client = self.pipeline.kube_client()
        batch_v1 = kube_apis.BatchV1Api(client)

        self.job_name = '{}-{}'.format(self.command[0], int(time.time() * 1000))
        job = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {'name': self.job_name},
            'spec': {
                'parallelism': self.parallelism,
                'ttlSecondsAfterFinished': 60 * 60, # cleanup pod after 1 hour
                'template': {
                    'spec': {
                        'imagePullSecrets': [{'name': 'regcred'}], # todo: abstract for user input
                        'containers': [{
                            'name': self.job_name,
                            'image': self.image,
                            'command': self.command,
                            'env': self.pipeline.env_list(),
                        }],
                'restartPolicy': 'OnFailure'}
            },
            'backoffLimit': 4}
        }

        response = batch_v1.create_namespaced_job(body=job, namespace="default")
        uid = response.metadata.labels["controller-uid"]
        logger.info("Job Submitted: {}: {}", self.job_name, uid)

        self.job_definition = response.to_dict()
        self.status = 'submitted'
        self.save()

        self.update_status(client, wait=wait)

    def job_status(self, api):
        response = api.read_namespaced_job_status(name=self.job_name, namespace="default")
        status = response.status

        logger.info("Job Status: {}: Active={}, Succeeded={}, Failed={}", self.id, status.active, status.succeeded, status.failed)
        if status.active:
            self.status = 'active'

        done = 0
        if status.succeeded is not None:
            done += status.succeeded
            self.succeeded = status.succeeded

        if status.failed is not None:
            done += status.failed
            self.failed = status.failed

        if not status.active and done == self.parallelism:
            self.status = 'completed'

        elif status.active is None and status.failed is None and status.succeeded is None:
            if status.conditions:
                self.status = 'failed'

        return status

    def update_status(self, client=None, logs=False, wait=False):
        if client is None:
            client = self.pipeline.kube_client()

        batch_v1 = kube_apis.BatchV1Api(client)

        while 1:
            self.pods = self.get_pods(client)

            try:
                stats = self.job_status(batch_v1)

            except ApiException as exc:
                if exc.status == 404:
                    self.status = 'killed'
                    self.save()
                    break

                else:
                    raise

            self.save()

            if self.status == 'completed':
                self.save_logs(client)
                break

            if not wait:
                if logs:
                    self.save_logs(client)

                break

            time.sleep(3)

    def get_pods(self, client):
        core_v1 = kube_apis.CoreV1Api(client)
        uid = self.job_definition['metadata']['labels']["controller-uid"]
        pods_list = core_v1.list_namespaced_pod(
            namespace="default", label_selector=f"controller-uid={uid}", timeout_seconds=10)
        logger.info('Pod Count: {}', len(pods_list.items))

        ret = []
        for pod in pods_list.items:
            ret.append(pod.metadata.name)

        return ret

    def save_logs(self, client):
        core_v1 = kube_apis.CoreV1Api(client)
        self.log_data = {}
        for pod_name in self.get_pods(client):
            log_response = core_v1.read_namespaced_pod_log(
                name=pod_name, namespace="default", _return_http_data_only=True, _preload_content=False)
            self.log_data[pod_name] = log_response.data.decode()

        self.save()

    def kill(self):
        client = self.pipeline.kube_client()
        batch_v1 = kube_apis.BatchV1Api(client)

        response = batch_v1.delete_namespaced_job(
            name=self.job_name,
            namespace="default",
            body=kube_apis.V1DeleteOptions(propagation_policy='Foreground', grace_period_seconds=0)
        )
        return response

    def watch_pod(self, pod_name, client=None, log=False):
        print(pod_name, log)
        if client is None:
            client = self.pipeline.kube_client()

        v1 = kube_apis.CoreV1Api(client)
        w = kube_watch.Watch()
        for e in w.stream(v1.read_namespaced_pod_log, name=pod_name, namespace='default'):
            if log:
                print('narf')
                print(e)

            else:
                yield e