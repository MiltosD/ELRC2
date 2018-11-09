from django.contrib import admin, messages
from django.contrib.auth.admin import csrf_protect_m
from metashare.processing.models import Processing


@admin.register(Processing)
class ProcessingObjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'job_uuid', 'service', 'source', 'elrc_resource',
                    'date_created', 'user', 'active', 'status',)

    readonly_fields = ('id', 'job_uuid', 'service', 'source', 'elrc_resource',
                       'status', 'date_created', 'user')

    list_filter = ('active', 'status', 'service', 'source')

    actions = ('deactivate_processing_object',)

    @csrf_protect_m
    def deactivate_processing_object(self, request, queryset):
        if request.user.is_superuser:
            successful = 0
            for obj in queryset:
                if obj.active:
                    obj.active = False
                    obj.save()
                    successful += 1
            if successful > 0:
                messages.info(request,
                              'Successfully deactivated {} processing objects.'.format(successful))
            else:
                messages.warning(request, 'No processing objects have been marked for deactivation')
        else:
            messages.error(request, 'You do not have the permission to '
                                    'perform this action for all selected resources.')

    deactivate_processing_object.short_description = "Deactivate Selected Processing Objects"
