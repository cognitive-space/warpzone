# Generated by Django 3.2.10 on 2022-01-12 19:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0048_rename_config_pipeline_config_old'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='shelix_log_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
