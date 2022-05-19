import datetime
import io
import json
import time
import random

from django.conf import settings
from django.core.cache import caches
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

import yaml
from cloudpathlib import S3Client
from dotenv import dotenv_values
from loguru import logger
from fernet_fields import EncryptedTextField

from kubernetes import client as kube_apis
from kubernetes import watch as kube_watch
from kubernetes.client import ApiClient, Configuration
from kubernetes.client.exceptions import ApiException
from kubernetes.config.kube_config import _get_kube_config_loader

from warpzone.shelix_api import StarHelixApi
import worlds.integrations.eks as eks


class Cluster(models.Model):
    CLUSTER_TYPES = (
        ('eks', 'AWS EKS'),
        ('do', 'Digital Ocean'),
    )

    name = models.CharField(max_length=70)
    slug = models.SlugField(max_length=70, unique=True)
    external_id = models.CharField(max_length=255)
    ctype = models.CharField('Cluster Type', max_length=5, choices=CLUSTER_TYPES)
    active = models.BooleanField(default=True)

    config = EncryptedTextField(help_text='kube config file', blank=True, null=True)

    def __str__(self):
        return self.name

    def kube_client(self):
        client_config = type.__call__(Configuration)
        loader = _get_kube_config_loader(config_dict=yaml.load(self.config, Loader=yaml.SafeLoader))
        loader.load_and_set(client_config)
        return ApiClient(configuration=client_config)


class Pipeline(models.Model):
    LOGGING = (
        ('kube', 'Kubernetes'),
        ('shelix', 'Star Helix'),
    )

    name = models.CharField(max_length=70)
    slug = models.SlugField(max_length=70, unique=True)

    worker_command = models.CharField(max_length=512)
    pre_command = models.CharField(max_length=512, blank=True, null=True)
    post_command = models.CharField(max_length=512, blank=True, null=True)
    workers = models.PositiveSmallIntegerField()

    config_old = EncryptedTextField(help_text='kube config file', blank=True, null=True)
    envs = EncryptedTextField(help_text='use .env format', blank=True, null=True)

    force_scaling = models.JSONField(blank=True, null=True)

    s3_storage_url = models.CharField(max_length=255, blank=True, null=True)
    logging = models.CharField(max_length=10, choices=LOGGING, default='kube')

    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return self.name

    def to_json(self):
        return {
            'name': self.name,
            'id': self.id,
            'slug': self.slug,
        }

    def kube_client(self):
        return self.cluster.kube_client()

    def list_pods(self, client=None):
        if client is None:
            client = self.kube_client()

        core_v1 = kube_apis.CoreV1Api(client)
        ret = core_v1.list_pod_for_all_namespaces(watch=False)
        return ret.items

    def running(self):
        if not hasattr(self, '_running'):
            self._running = Job.objects.filter(
                status__in=Job.STATUS_RUNNING,
                pipeline=self,
            ).first()

        return self._running

    def full_command(self, cmd):
        ret = []
        if self.pre_command:
            ret += self.pre_command.split(' ')

        ret += cmd

        if self.post_command:
            ret += self.post_command.split(' ')

        return ret

    def start_pipeline(self, image, job_envs=None):
        qjob = Job.objects.filter(
            image=image,
            status__in=Job.STATUS_RUNNING,
            pipeline=self,
        ).first()

        if qjob:
            qjob.update_status()
            if qjob.status in qjob.STATUS_DONE:
                qjob = None

        if qjob is None:
            qjob = Job(
                command=self.worker_command.split(' '),
                image=image,
                parallelism=self.workers,
                pipeline=self,
                envs=job_envs,
                job_type_id=1,
            )
            qjob.save()
            qjob.run()

        return qjob


    def env_list(self, local_envs_dict=None, job_envs=None):
        ret = []
        if local_envs_dict:
            for key, value in local_envs_dict.items():
                ret.append({'name': key, 'value': value})

        if self.envs:
            stream = io.StringIO(self.envs)
            for name, value in dotenv_values(stream=stream).items():
                ret.append({'name': name, 'value': value})

        if job_envs:
            stream = io.StringIO(job_envs)
            for name, value in dotenv_values(stream=stream).items():
                ret.append({'name': name, 'value': value})

        return ret

    def s3_storage_args(self):
        ret = {}
        if self.envs:
            stream = io.StringIO(self.envs)
            envs = dotenv_values(stream=stream)

            if 'AWS_ACCESS_KEY_ID' in envs:
                ret['aws_access_key_id'] = envs['AWS_ACCESS_KEY_ID']

            if 'AWS_SECRET_ACCESS_KEY' in envs:
                ret['aws_secret_access_key'] = envs['AWS_SECRET_ACCESS_KEY']

            if 'AWS_S3_ENDPOINT_URL' in envs:
                ret['endpoint_url'] = envs['AWS_S3_ENDPOINT_URL']

        return ret

    def get_job_storage(self):
        if self.s3_storage_url:
            client = S3Client(**self.s3_storage_args())
            return client.CloudPath(self.s3_storage_url)


class JobType(models.Model):
    name = models.CharField(max_length=70)
    cpu_request = models.CharField(max_length=25, blank=True, null=True)
    memory_request = models.CharField(max_length=25, blank=True, null=True)
    cpu_limit = models.CharField(max_length=25, blank=True, null=True)
    memory_limit = models.CharField(max_length=25, blank=True, null=True)
    worker_node_selector = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name


class Job(models.Model):
    STATUS = (
        ('created', 'Created'),
        ('submitted', 'Submitted'),
        ('downloading', 'Downloading Container'),
        ('active', 'Active'),
        ('killed', 'Killed'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
    )

    STATUS_RUNNING = ['active', 'created', 'submitted', 'downloading']
    STATUS_DONE = ['completed', 'killed', 'failed']

    command = ArrayField(models.CharField(max_length=255))
    image = models.CharField(max_length=255)
    envs = EncryptedTextField(help_text='use .env format', blank=True, null=True)
    parallelism = models.PositiveSmallIntegerField(default=1)

    succeeded = models.PositiveSmallIntegerField(default=0)
    failed = models.PositiveSmallIntegerField(default=0)

    job_name = models.CharField(max_length=255, blank=True, null=True)
    job_definition = models.JSONField(blank=True, null=True, encoder=DjangoJSONEncoder)
    shelix_log_id = models.CharField(max_length=255, blank=True, null=True)

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE)
    job_type = models.ForeignKey(JobType, blank=True, null=True, on_delete=models.SET_NULL)

    status = models.CharField(max_length=25, choices=STATUS, default='created')

    pods = ArrayField(models.CharField(max_length=255), blank=True, null=True)
    pod_watchers = ArrayField(models.CharField(max_length=255), blank=True, null=True)

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

    @property
    def downloadable(self):
        if self.status in self.STATUS_DONE:
            if self.pipeline.get_job_storage():
                return True

        return False

    def to_json(self):
        return {
            'job_name': self.job_name,
            'id': self.id,
            'status': self.get_status_display(),
            'pipeline': self.pipeline.to_json(),
            'pods': self.pods,
            'log_data': self.complete_logs,
            'modified': self.modified.isoformat(),
            'created': self.created.isoformat(),
            'downloadable': self.downloadable,
            'envs': self.envs,
        }

    @property
    def cmd(self):
        if self.command:
            return ' '.join(self.command)

        return ''

    @property
    def complete_logs(self):
        if self.status in self.STATUS_DONE:
            logs = {}
            for log in CompletedLog.objects.filter(job=self):
                if log.pod is None:
                    logs['all'] = log.log_file.url

                else:
                    logs[log.pod] = log.log_file.url

            return logs

        return {}

    def pod_spec(self):
        job_path = self.job_name
        local_envs = {}

        if settings.SHELIX_ENABLED and self.pipeline.logging == 'shelix':
            data = StarHelixApi.start_log(self.job_name)
            self.shelix_log_id = str(data['log_id'])
            self.save()
            local_envs['SHELIX_LOGID'] = self.shelix_log_id
            local_envs['SHELIX_TOKEN'] = settings.SHELIX_TOKEN
            local_envs['SHELIX_PREFIX'] = 'worker'
            local_envs['SHELIX_TS_PREFIX'] = '1'
            local_envs['SHELIX_STORE_PREFIX'] = '1'
            local_envs['PYTHONUNBUFFERED'] = '1'

        ret = {
            'imagePullSecrets': [{'name': 'regcred'}], # todo: abstract for user input
            'containers': [{
                'name': self.job_name,
                'image': self.image,
                'command': self.pipeline.full_command(self.command),
                'env': self.pipeline.env_list(local_envs, self.envs),
            }],
            'restartPolicy': 'OnFailure',
        }

        if self.job_type:
            ret['containers'][0]['resources'] = {}
            if self.job_type.memory_request or self.job_type.cpu_request:
                ret['containers'][0]['resources']['requests'] = {}
                if self.job_type.memory_request:
                    ret['containers'][0]['resources']['requests']['memory'] = self.job_type.memory_request

                if self.job_type.cpu_request:
                    ret['containers'][0]['resources']['requests']['cpu'] = self.job_type.cpu_request

            if self.job_type.memory_limit or self.job_type.cpu_limit:
                ret['containers'][0]['resources']['limits'] = {}
                if self.job_type.memory_limit:
                    ret['containers'][0]['resources']['limits']['memory'] = self.job_type.memory_limit

                if self.job_type.cpu_limit:
                    ret['containers'][0]['resources']['limits']['cpu'] = self.job_type.cpu_limit

            if self.job_type.worker_node_selector:
                key, value = self.pipeline.worker_node_selector.split('=')
                ret['nodeSelector'] = {key: value}

        return ret

    def run(self, wait=False):
        client = self.pipeline.kube_client()
        batch_v1 = kube_apis.BatchV1Api(client)

        job_name = self.command[0]
        job_name = job_name.split("/")[-1]
        job_name = job_name.replace(".", "-")
        self.job_name = '{}-{}'.format(job_name, int(time.time() * 1000))

        job = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {'name': self.job_name},
            'spec': {
                'parallelism': self.parallelism,
                # 'completions': self.parallelism,
                'ttlSecondsAfterFinished': 60 * 60, # cleanup pod after 1 hour
                'template': {
                    'spec': self.pod_spec()
                },
                'backoffLimit': 4
            }
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
        from worlds.tasks import watch_log

        if client is None:
            client = self.pipeline.kube_client()

        batch_v1 = kube_apis.BatchV1Api(client)

        while 1:
            if not self.pods:
                self.pods = []

            for p in self.get_pods(client):
                if p not in self.pods:
                    self.pods.append(p)

            if not self.pod_watchers:
                self.pod_watchers = []

            for p in self.pods:
                if p not in self.pod_watchers:
                    watch_log(self.id, p)
                    self.pod_watchers.append(p)

            try:
                stats = self.job_status(batch_v1)

            except ApiException as exc:
                if exc.status == 404:
                    self.status = 'killed'
                    self.save()
                    self.save_logs(client)
                    break

                else:
                    raise

            self.save()

            if self.status in self.STATUS_DONE:
                try:
                    self.save_logs(client)

                except:
                    pass

                self.fix_logs()
                break

            if not wait:
                break

            time.sleep(3)

    def log(self, text):
        if self.shelix_log_id:
            now = datetime.datetime.now(datetime.timezone.utc)
            StarHelixApi.save_log(
                self.shelix_log_id,
                f'warpzone[server]: {now.isoformat()}: {text}'
            )

    def end_logs(self):
        if self.shelix_log_id:
            StarHelixApi.end_log(self.shelix_log_id)

            from worlds.tasks import end_shelix_log
            end_shelix_log(self.id)

    def fix_logs(self):
        if self.shelix_log_id:
            return

        for p in self.pods:
            log = CompletedLog.objects.filter(job=self, pod=p).first()
            if log and log.log_file:
                streamed = None
                with log.log_file.open('r') as fh:
                    line = fh.readline()
                    if line.startswith('unable to retrieve container logs for docker://'):
                        streamlog = StreamLog.objects.filter(job=self, pod=p).first()
                        if streamlog:
                            streamed = streamlog.log_file

                if streamed:
                    with streamed.open('r') as rh:
                        with log.log_file.open('w') as wh:
                            while 1:
                                data = rh.read(1024)
                                if data:
                                    wh.write(data)

                                else:
                                    break


    def get_pods(self, client):
        core_v1 = kube_apis.CoreV1Api(client)
        try:
            uid = self.job_definition['metadata']['labels']["controller-uid"]

        except TypeError:
            return []

        pods_list = core_v1.list_namespaced_pod(
            namespace="default", label_selector=f"controller-uid={uid}", timeout_seconds=10)
        logger.info('Pod Count: {}', len(pods_list.items))

        ret = []
        for pod in pods_list.items:
            ret.append(pod.metadata.name)

        return ret

    def save_logs(self, client):
        if self.shelix_log_id:
            return self.end_logs()

        elif self.status == 'killed':
            for slog in StreamLog.objects.filter(job=self):
                log = CompletedLog.objects.filter(job=self, pod=slog.pod).first()
                if not log:
                    log = CompletedLog(job=self, pod=slog.pod)

                log.log_file = slog.log_file
                log.save()

        else:
            core_v1 = kube_apis.CoreV1Api(client)
            for pod_name in self.get_pods(client):
                log_response = core_v1.read_namespaced_pod_log(
                    name=pod_name, namespace="default", _return_http_data_only=True, _preload_content=False)

                log = CompletedLog.objects.filter(job=self, pod=pod_name).first()
                if not log:
                    log = CompletedLog(job=self, pod=pod_name)

                log.log_file.save(f'{pod_name}.completed.log', content=ContentFile(log_response.data), save=False)
                log.save()

    def kill(self):
        client = self.pipeline.kube_client()
        batch_v1 = kube_apis.BatchV1Api(client)

        response = batch_v1.delete_namespaced_job(
            name=self.job_name,
            namespace="default",
            body=kube_apis.V1DeleteOptions(propagation_policy='Foreground', grace_period_seconds=0)
        )
        return response

    def watch_pod(self, pod_name, client=None):
        if client is None:
            client = self.pipeline.kube_client()

        v1 = kube_apis.CoreV1Api(client)
        w = kube_watch.Watch()

        try:
            for e in w.stream(v1.read_namespaced_pod_log, name=pod_name, namespace='default'):
                yield e

        except ApiException as exc:
            msg = exc.body.decode()

            if exc.status == 400:
                if 'ContainerCreating' in json.loads(msg)['message']:
                    self.status = 'downloading'
                    self.save()
                    self.log('Waiting for container creation\n')

                else:
                    self.log(f'Error: {msg}\n')
                    raise

            else:
                self.log(f'Error: {msg}\n')
                raise


class CompletedLog(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    pod = models.CharField(max_length=255, blank=True, null=True)
    log_file = models.FileField(upload_to='warpzone/%Y/%m/%d/', blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        unique_together = [['job', 'pod']]

    def __str__(self):
        return self.name

    @property
    def name(self):
        if self.pod is None:
            return self.job.name

        return self.pod


class StreamLog(models.Model):
    STATUS = (
        ('created', 'Created'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    pod = models.CharField(max_length=255)
    log_file = models.FileField(upload_to='warpzone/%Y/%m/%d/', blank=True, null=True)
    lines = models.PositiveIntegerField(default=0)
    retries = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=25, choices=STATUS, default='created')

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-modified']
        unique_together = [['job', 'pod']]

    def __str__(self):
        return self.pod
