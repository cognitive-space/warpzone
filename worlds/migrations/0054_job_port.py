# Generated by Django 3.2.10 on 2022-04-14 20:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0053_remove_pipeline_scale_down_delay'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='port',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
