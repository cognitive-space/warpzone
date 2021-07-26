from django.contrib import admin

from worlds.models import Pipeline


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'workers')
    search_fields = ('name', 'slug', 'worker_command')
