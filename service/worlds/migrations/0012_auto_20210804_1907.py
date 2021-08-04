# Generated by Django 3.2.6 on 2021-08-04 19:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0011_alter_job_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='failed',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='job',
            name='succeeded',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
