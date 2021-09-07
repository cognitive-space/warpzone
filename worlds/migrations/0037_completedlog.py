# Generated by Django 3.2.6 on 2021-09-07 15:17

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0036_remove_streamlog_logs'),
    ]

    operations = [
        migrations.CreateModel(
            name='CompletedLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pod', models.CharField(max_length=255)),
                ('log_file', models.FileField(blank=True, null=True, upload_to='warpzone/%Y/%m/%d/')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='worlds.job')),
            ],
            options={
                'ordering': ['-created'],
                'unique_together': {('job', 'pod')},
            },
        ),
    ]
