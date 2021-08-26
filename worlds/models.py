import io
import time
import random

from django.db import models
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.postgres.fields import ArrayField
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

import worlds.integrations.eks as eks

INTEGRATIONS = {
    'eks': eks
}


class Pipeline(models.Model):
    name = models.CharField(max_length=70)
    slug = models.SlugField(max_length=70, unique=True)

    worker_command = models.CharField(max_length=512)
    pre_command = models.CharField(max_length=512, blank=True, null=True)
    post_command = models.CharField(max_length=512, blank=True, null=True)
    workers = models.PositiveSmallIntegerField()

    scale_down_delay = models.PositiveSmallIntegerField(default=1200)
    worker_node_selector = models.CharField(max_length=255, blank=True, null=True)
    master_node_selector = models.CharField(max_length=255, blank=True, null=True)

    config = EncryptedTextField(help_text='kube config file', blank=True, null=True)
    envs = EncryptedTextField(help_text='use .env format', blank=True, null=True)

    force_scaling = models.JSONField(blank=True, null=True)

    s3_storage_url = models.CharField(max_length=255, blank=True, null=True)

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

    def list_pods(self, client=None):
        if client is None:
            client = self.kube_client()

        core_v1 = kube_apis.CoreV1Api(client)
        ret = core_v1.list_pod_for_all_namespaces(watch=False)
        return ret.items

    def running(self):
        qjob = Job.objects.filter(
            status__in=Job.STATUS_RUNNING,
            pipeline=self,
            job_type='queue'
        ).first()

        return qjob

    def full_command(self, cmd):
        ret = []
        if self.pre_command:
            ret += self.pre_command.split(' ')

        ret += cmd

        if self.post_command:
            ret += self.post_command.split(' ')

        return ret

    def start_pipeline(self, image, job_envs=None):
        qjob = Job(
            command=self.worker_command.split(' '),
            image=image,
            parallelism=self.workers,
            pipeline=self,
            job_type='queue',
            port=random.randint(10000, 30000),
            envs=job_envs,
        )
        qjob.save()
        self.scale_up()
        qjob.run()
        return qjob

    def run_job(self, image, job_command, job_envs=None, wait=False):
        qjob = Job.objects.filter(
            image=image,
            status__in=Job.STATUS_RUNNING,
            pipeline=self,
            job_type='queue'
        ).first()

        if qjob:
            qjob.update_status()
            if qjob.status in qjob.STATUS_DONE:
                qjob = None

        if qjob is None:
            qjob = self.start_pipeline(image, job_envs)

        time.sleep(0.1)

        job = Job(
            command=job_command.split(' '),
            image=image,
            parallelism=1,
            pipeline=self,
            job_type='job',
            queue=qjob,
            port=random.randint(40000, 65535),
            envs=job_envs,
        )
        job.save()
        job.run()
        return qjob, job

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

    def scale_up(self):
        if self.force_scaling:
            for key, mod in INTEGRATIONS.items():
                if key in self.force_scaling:
                    return mod.scale_up(self, self.force_scaling[key])

    def scale_down(self):
        if self.force_scaling and self.scale_down_delay:
            from worlds.tasks import scale_down
            scale_down.schedule((self.id,), delay=self.scale_down_delay)

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

    STATUS_RUNNING = ['active', 'created', 'submitted']
    STATUS_DONE = ['completed', 'killed', 'failed']

    JOB_TYPES = (
        ('queue', 'Queue'),
        ('job', 'Job'),
    )

    command = ArrayField(models.CharField(max_length=255))
    image = models.CharField(max_length=255)
    envs = EncryptedTextField(help_text='use .env format', blank=True, null=True)
    parallelism = models.PositiveSmallIntegerField(default=1)

    succeeded = models.PositiveSmallIntegerField(default=0)
    failed = models.PositiveSmallIntegerField(default=0)

    job_name = models.CharField(max_length=255, blank=True, null=True)
    job_definition = models.JSONField(blank=True, null=True, encoder=DjangoJSONEncoder)
    job_type = models.CharField(max_length=10, choices=JOB_TYPES)
    queue = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    port = models.PositiveIntegerField()

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE)

    status = models.CharField(max_length=25, choices=STATUS, default='created')

    pods = ArrayField(models.CharField(max_length=255), blank=True, null=True)
    pod_watchers = ArrayField(models.CharField(max_length=255), blank=True, null=True)

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

    @property
    def downloadable(self):
        if self.job_type == 'job' and self.status in self.STATUS_DONE:
            if self.pipeline.get_job_storage():
                return True

        return False

    def to_json(self):
        q = None
        if self.queue:
            q = self.queue.id

        return {
            'job_name': self.job_name,
            'id': self.id,
            'status': self.get_status_display(),
            'pipeline': self.pipeline.to_json(),
            'pods': self.pods,
            'log_data': self.complete_logs,
            'modified': self.modified.isoformat(),
            'created': self.created.isoformat(),
            'job_type': self.job_type,
            'queue': q,
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
            return self.log_data

        return {}

    def pod_spec(self):
        job_path = self.job_name
        local_envs = {}
        if self.job_type == 'job':
            local_envs = {
                'JOB_NAME': self.job_name,
                'JOB_PATH': job_path
            }

        ret = {
            'imagePullSecrets': [{'name': 'regcred'}], # todo: abstract for user input
            'containers': [{
                'name': self.job_name,
                'image': self.image,
                'command': self.pipeline.full_command(self.command),
                'env': self.pipeline.env_list(local_envs, self.envs),
                'ports': [{'hostPort': self.port, 'containerPort': self.port}] # this is hack to get one pod per node
            }],
            'restartPolicy': 'OnFailure'
        }

        if self.job_type == 'queue' and self.pipeline.worker_node_selector:
            key, value = self.pipeline.worker_node_selector.split('=')
            ret['nodeSelector'] = {key: value}

        elif self.job_type == 'job' and self.pipeline.master_node_selector:
            key, value = self.pipeline.master_node_selector.split('=')
            ret['nodeSelector'] = {key: value}

        return ret

    def run(self, wait=False):
        client = self.pipeline.kube_client()
        batch_v1 = kube_apis.BatchV1Api(client)

        self.job_name = '{}-{}-{}'.format(self.job_type, self.command[0], int(time.time() * 1000))

        job = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {'name': self.job_name},
            'spec': {
                'parallelism': self.parallelism,
                # 'completions': self.parallelism,
                'ttlSecondsAfterFinished': 60 * 60, # cleanup pod after 1 hour
                'template': {'spec': self.pod_spec()},
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
                if self.job_type == 'queue':
                    self.pipeline.scale_down()

                break

            if not wait:
                if logs:
                    self.save_logs(client)

                break

            time.sleep(3)

    def fix_logs(self):
        for p in self.pods:
            logs = self.log_data.get(p, None)
            if not logs or logs.startswith('unable to retrieve container logs for docker://'):
                streamlog = StreamLog.objects.filter(job=self, pod=p).first()
                if streamlog:
                    self.log_data[streamlog.pod] = streamlog.logs

        self.save()

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
            logtext = log_response.data.decode()
            self.log_data[pod_name] = logtext

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

    def watch_pod(self, pod_name, client=None):
        if client is None:
            client = self.pipeline.kube_client()

        v1 = kube_apis.CoreV1Api(client)
        w = kube_watch.Watch()
        for e in w.stream(v1.read_namespaced_pod_log, name=pod_name, namespace='default'):
            yield e

class StreamLog(models.Model):
    STATUS = (
        ('created', 'Created'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    pod = models.CharField(max_length=255)
    logs = models.TextField(blank=True, null=True)
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
