# Generated by Django 3.2.6 on 2021-08-18 22:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0017_job_pods'),
    ]

    operations = [
        migrations.AddField(
            model_name='pipeline',
            name='force_scaling',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
