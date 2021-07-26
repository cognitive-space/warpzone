from django.db import models

from fernet_fields import EncryptedTextField


class Pipeline(models.Model):
    name = models.CharField(max_length=70)
    slug = models.SlugField(max_length=70, unique=True)

    worker_command = models.CharField(max_length=512)
    workers = models.PositiveSmallIntegerField()

    envs = EncryptedTextField(help_text='use .env format')

    def __str__(self):
        return self.name
