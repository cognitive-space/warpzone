# Generated by Django 3.2.6 on 2021-08-06 18:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0013_auto_20210804_1910'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='job_type',
            field=models.CharField(choices=[('queue', 'Queue'), ('job', 'Job')], default='job', max_length=10),
            preserve_default=False,
        ),
    ]
