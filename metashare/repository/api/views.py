from django.http import HttpResponseForbidden, HttpResponse
from metashare.repository.editor.resource_editor import ResourceModelAdmin
from metashare.repository.models import resourceInfoType_model

admin = ResourceModelAdmin(model=resourceInfoType_model, admin_site=None)


def get_data(request, object_id):
    """
    Provide direct resource dataset download form API
    :param request: resquest from API
    :param object_id: resource id to download dataset from
    :return: dataset in zip format or 403
    """
    resource = resourceInfoType_model.objects.get(pk=object_id)
    if resource and (request.user.is_superuser or request.user in resource.owners.all()):
        data = admin.datadl(request, object_id)
        return data
    else:
        return HttpResponseForbidden()


def upload_data(request, object_id):
    """
    Provide direct resource dataset download form API
    :param request: resquest from API
    :param object_id: resource id to upload zip dataset to
    """

    resource = resourceInfoType_model.objects.get(pk=object_id)
    if resource and (request.user.is_superuser or request.user in resource.owners.all()):

        _storage_folder = resource.storage_object._storage_folder()

        _out_filename = '{}/archive.zip'.format(_storage_folder)

        dataset = request.FILES['resource']
        with open(_out_filename, 'wb') as _out_file:
            # pylint: disable-msg=E1101
            for _chunk in dataset.chunks():
                _out_file.write(_chunk)

            # Update the corresponding StorageObject to update its
            # download data checksum.
        resource.storage_object.compute_checksum()
        resource.storage_object.save()

        return HttpResponse("Dataset {} has been uploaded".format(dataset))
        # return admin.uploaddata_view(request, object_id)
    else:
        return HttpResponseForbidden()


def get_xml(request, object_id):
    return admin.exportxml(request, object_id)
