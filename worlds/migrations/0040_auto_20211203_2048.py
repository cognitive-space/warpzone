# Generated by Django 3.2.9 on 2021-12-03 20:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0039_auto_20211203_1331'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pipeline',
            name='pods_per_node',
        ),
        migrations.AddField(
            model_name='pipeline',
            name='memory_request',
            field=models.CharField(blank=True, max_length=25, null=True),
        ),
    ]