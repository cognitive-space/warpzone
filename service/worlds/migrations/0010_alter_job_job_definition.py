# Generated by Django 3.2.6 on 2021-08-04 18:09

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0009_job_job_definition'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='job_definition',
            field=models.JSONField(blank=True, encoder=django.core.serializers.json.DjangoJSONEncoder, null=True),
        ),
    ]
