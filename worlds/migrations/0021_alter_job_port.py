# Generated by Django 3.2.6 on 2021-08-19 19:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0020_job_port'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='port',
            field=models.PositiveIntegerField(),
        ),
    ]