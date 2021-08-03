import time

from django.db import models

import yaml
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

    @property
    def kube_client(self):
        client_config = type.__call__(Configuration)
        loader = _get_kube_config_loader(config_dict=yaml.load(self.config, Loader=yaml.SafeLoader))

        loader.load_and_set(client_config)
        return ApiClient(configuration=client_config)

    def run_job(self, image, command, wait=False):
        batch_v1 = kube_apis.BatchV1Api(self.kube_client)

        job_name = '{}-{}'.format(command[0], int(time.time()))
        job = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {'name': job_name},
            'spec': {
                'template': {
                    'spec': {
                        'containers': [{
                            'name': job_name,
                            'image': image,
                            'command': command
                        }],
                'restartPolicy': 'Never'}
            },
            'backoffLimit': 4}
        }

        response = batch_v1.create_namespaced_job(body=job, namespace="default")
        if wait:
            while 1:
                status = self.job_status(batch_v1, job_name)
                print("Job created. status={}".format(status))
                if status.succeeded is not None or status.failed is not None:
                    return response

                time.sleep(3)

        return response

    @staticmethod
    def job_status(api, job_name):
        response = api.read_namespaced_job_status(name=job_name, namespace="default")
        return response.status

# 'uid': 'bf7a0696-b2fd-4f20-947f-f44e271780d2'},
