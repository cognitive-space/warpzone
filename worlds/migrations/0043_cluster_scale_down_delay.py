# Generated by Django 3.2.10 on 2021-12-10 21:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0042_cluster_ctype'),
    ]

    operations = [
        migrations.AddField(
            model_name='cluster',
            name='scale_down_delay',
            field=models.PositiveSmallIntegerField(default=1200),
        ),
    ]
