# Generated by Django 3.2.10 on 2021-12-10 17:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0041_cluster_nodepool'),
    ]

    operations = [
        migrations.AddField(
            model_name='cluster',
            name='ctype',
            field=models.CharField(choices=[('eks', 'AWS EKS'), ('do', 'Digital Ocean')], default='eks', max_length=5, verbose_name='Cluster Type'),
            preserve_default=False,
        ),
    ]