# Generated by Django 3.2.6 on 2021-08-06 22:50

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0016_auto_20210806_2014'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='pods',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=255), blank=True, null=True, size=None),
        ),
    ]
