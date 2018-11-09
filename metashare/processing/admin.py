from django.contrib import admin
from metashare.processing.models import Processing


@admin.register(Processing)
class ProcessingObjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'job_uuid', 'service', 'source', 'elrc_resource',
                    'date_created', 'user', 'active', 'status',)

    readonly_fields = ('id', 'job_uuid', 'service', 'source', 'elrc_resource',
                       'status', 'date_created', 'user')

    list_filter = ('active', 'status',)
