from django.conf import settings
from django.contrib import admin
from django.db.models import JSONField
from django import forms
from django.utils.html import mark_safe

from django_json_widget.widgets import JSONEditorWidget

from worlds.models import Pipeline, Job, StreamLog, CompletedLog, Cluster, JobType


@admin.register(JobType)
class JobTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'cpu_request', 'memory_request', 'cpu_limit', 'memory_limit')
    search_fields = ('name',)


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    save_as = True


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'workers')
    search_fields = ('name', 'slug', 'worker_command')
    save_as = True

    raw_id_fields = ('cluster',)

    formfield_overrides = {
        JSONField: {'widget': JSONEditorWidget()},
    }


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('name', '_image', 'parallelism', 'succeeded', 'failed', 'status', 'created', '_actions')
    list_filter = ('status', 'modified', 'created')
    search_fields = ('command', 'image', 'job_name')
    formfield_overrides = {
        JSONField: {'widget': JSONEditorWidget(options={'mode': 'view'})},
    }

    raw_id_fields = ('pipeline',)
    readonly_fields = ('succeeded', 'failed', 'status')

    def _actions(self, obj):
        if obj:
            return mark_safe(f'<a href="/worlds/job/{obj.id}/" target="_blank">view</a>')

    def _image(self, obj):
        img = obj.image

        if settings.CONTAINER_REPO:
            img = img.replace(settings.CONTAINER_REPO + '/', '')

        img = img.split(':')
        if len(img) > 1:
            img[-1] = img[-1][:8]

        return ":".join(img)


@admin.register(CompletedLog)
class CompletedLogAdmin(admin.ModelAdmin):
    list_display= ('name', 'job', 'created')
    search_fields = ('pod', 'job__job_name')
    date_hierarchy = 'created'
    raw_id_fields = ('job',)


@admin.register(StreamLog)
class StreamLogAdmin(admin.ModelAdmin):
    list_display= ('pod', 'job', 'lines', 'status', 'modified')
    search_fields = ('pod', 'job__job_name')
    date_hierarchy = 'modified'
    raw_id_fields = ('job',)
