# Generated by Django 3.2.10 on 2021-12-10 21:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0044_nodepool_current_size'),
    ]

    operations = [
        migrations.AddField(
            model_name='pipeline',
            name='cluster',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='worlds.cluster'),
        ),
    ]
