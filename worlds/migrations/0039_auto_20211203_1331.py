# Generated by Django 3.2.9 on 2021-12-03 13:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0038_remove_job_log_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='port',
        ),
        migrations.AddField(
            model_name='pipeline',
            name='pods_per_node',
            field=models.PositiveIntegerField(default=2),
        ),
    ]