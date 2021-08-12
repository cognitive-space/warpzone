from django.conf import settings
from django.contrib import admin
from django.db.models import JSONField
from django import forms

from django_json_widget.widgets import JSONEditorWidget

from worlds.models import Pipeline, Job


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'workers')
    search_fields = ('name', 'slug', 'worker_command')


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('name', '_image', 'parallelism', 'succeeded', 'failed', 'job_type', 'status', 'created')
    list_filter = ('status', 'job_type', 'modified', 'created')
    search_fields = ('command', 'image', 'job_name')
    formfield_overrides = {
        JSONField: {'widget': JSONEditorWidget(options={'mode': 'view'})},
    }

    readonly_fields = ('succeeded', 'failed', 'status')
    raw_id_fields = ('queue',)

    def _image(self, obj):
        img = obj.image

        if settings.CONTAINER_REPO:
            img = img.replace(settings.CONTAINER_REPO + '/', '')

        img = img.split(':')
        if len(img) > 1:
            img[-1] = img[-1][:8]

        return ":".join(img)
