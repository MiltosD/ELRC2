from django import template
from metashare.repository.models import resourceInfoType_model

register = template.Library()


@register.filter(name='get_resource_name')
def get_resource_name(res_id):
    info = dict()
    resource = resourceInfoType_model.objects.get(id=res_id)
    try:
        return resource.identificationInfo.resourceName['en']
    except KeyError:
        return resource.identificationInfo.resourceName[
            resource.identificationInfo.resourceName.keys()[0]
        ]


@register.filter(name='get_resource_url')
def get_resource_name(res_id):
    resource = resourceInfoType_model.objects.get(id=res_id)
    return resource.get_absolute_url()


@register.filter(name='get_resource_status')
def get_resource_status(res_id):
    resource = resourceInfoType_model.objects.get(id=res_id)
    return resource.storage_object.publication_status
