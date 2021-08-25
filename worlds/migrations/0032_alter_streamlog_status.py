# Generated by Django 3.2.6 on 2021-08-25 20:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worlds', '0031_streamlog_retries'),
    ]

    operations = [
        migrations.AlterField(
            model_name='streamlog',
            name='status',
            field=models.CharField(choices=[('created', 'Created'), ('completed', 'Completed'), ('failed', 'Failed')], default='created', max_length=25),
        ),
    ]
