import time

from django.db import models
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.postgres.fields import ArrayField

import yaml
from loguru import logger
from fernet_fields import EncryptedTextField

from kubernetes import client as kube_apis
from kubernetes.client import ApiClient, Configuration
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

    def kube_client(self):
        client_config = type.__call__(Configuration)
        loader = _get_kube_config_loader(config_dict=yaml.load(self.config, Loader=yaml.SafeLoader))

        loader.load_and_set(client_config)
        return ApiClient(configuration=client_config)

    def run_job(self, image, command, parallelism=1, wait=False):
        job = Job(
            command=command,
            image=image,
            parallelism=parallelism,
            pipeline=self,
        )
        job.save()
        job.run(wait=wait)
        return job


class Job(models.Model):
    STATUS = (
        ('created', 'Created'),
        ('submitted', 'Submitted'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    )

    command = ArrayField(models.CharField(max_length=255))
    image = models.CharField(max_length=255)
    parallelism = models.PositiveSmallIntegerField(default=1)

    succeeded = models.PositiveSmallIntegerField(default=0)
    failed = models.PositiveSmallIntegerField(default=0)

    job_name = models.CharField(max_length=255, blank=True, null=True)
    job_definition = models.JSONField(blank=True, null=True, encoder=DjangoJSONEncoder)

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE)

    status = models.CharField(max_length=255, choices=STATUS, default='created')

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

    def run(self, wait=False):
        client = self.pipeline.kube_client()
        batch_v1 = kube_apis.BatchV1Api(client)

        self.job_name = '{}-{}'.format(self.command[0], int(time.time()))
        job = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {'name': self.job_name},
            'spec': {
                'parallelism': self.parallelism,
                'template': {
                    'spec': {
                        'containers': [{
                            'name': self.job_name,
                            'image': self.image,
                            'command': self.command
                        }],
                'restartPolicy': 'Never'}
            },
            'backoffLimit': 4}
        }

        response = batch_v1.create_namespaced_job(body=job, namespace="default")
        uid = response.metadata.labels["controller-uid"]
        logger.info("Job Submitted: {}: {}", self.job_name, uid)

        self.job_definition = response.to_dict()
        self.status = 'submitted'
        self.save()

        if wait:
            self.wait(client)

    def job_status(self, api):
        response = api.read_namespaced_job_status(name=self.job_name, namespace="default")
        status = response.status

        logger.info("Job Status: Active={}, Succeeded={}, Failed={}", status.active, status.succeeded, status.failed)
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

        return status

    def wait(self, client=None):
        if client is None:
            client = self.pipeline.kube_client()

        batch_v1 = kube_apis.BatchV1Api(client)
        while 1:
            stats = self.job_status(batch_v1)
            self.save()

            if self.status == 'completed':
                break

            time.sleep(3)

        self.save_logs(client)

    def save_logs(self, client):
        core_v1 = kube_apis.CoreV1Api(client)
        uid = self.job_definition['metadata']['labels']["controller-uid"]
        pods_list = core_v1.list_namespaced_pod(
            namespace="default", label_selector=f"controller-uid={uid}", timeout_seconds=10)
        logger.info('Pod Count: {}', len(pods_list.items))

        self.log_data = []
        for pod in pods_list.items:
            pod_name = pod.metadata.name
            log_response = core_v1.read_namespaced_pod_log(
                name=pod_name, namespace="default", _return_http_data_only=True, _preload_content=False)
            self.log_data.append(log_response.data.decode())

        self.save()


