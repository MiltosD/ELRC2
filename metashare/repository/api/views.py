from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse, HttpResponseBadRequest
from django.utils.encoding import smart_str

from metashare.repository.editor.resource_editor import ResourceModelAdmin
from metashare.repository.fields import best_lang_value_retriever
from metashare.repository.models import resourceInfoType_model
from metashare.repository.templatetags.is_member import is_member

admin = ResourceModelAdmin(model=resourceInfoType_model, admin_site=None)

publication_status = {
    'i': 'INTERNAL',
    'g': 'INGESTED',
    'p': 'PUBLISHED'
}


def _get_user_queryset(user):
    queryset = resourceInfoType_model.objects.filter(storage_object__deleted=False)
    if user.is_superuser or is_member(user, 'elrcReviewers'):
        return queryset
    elif is_member(user, 'ecmembers'):
        return queryset.filter(storage_object__publication_status__in=['g', 'p'])
    else:
        return queryset.filter(owners__in=[user])


def get_data(request, object_id):
    """
    Provide direct resource dataset download form API
    :param request: resquest from API
    :param object_id: resource id to download dataset from
    :return: dataset in zip format or 403
    """
    resource = resourceInfoType_model.objects.get(pk=object_id)
    if resource and (request.user.is_superuser or request.user in resource.owners.all()
                     or is_member(request.user, 'elrcReviewers')):
        data = admin.datadl(request, object_id)
        return data
    else:
        return HttpResponseForbidden()


def upload_data(request, object_id):
    """
    Provide direct resource dataset download form API
    :param request: request from API
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


@login_required
def get_xml(request, object_id=None):
    """
    :param request: request from API
    :param object_id: resource id
    :param my: boolean for user own resources
    :return:
    """
    if object_id:
        return admin.exportxml(request, object_id)
    else:
        return HttpResponseBadRequest(
            content='No resource id provided'
        )


@login_required
def list(request):
    response = ""
    queryset = _get_user_queryset(request.user)
    for q in queryset:
        response += u"{}\t{}\t{}\n".format(
            q.id,
            best_lang_value_retriever(q.identificationInfo.resourceName),
            publication_status.get(q.storage_object.publication_status))
    response += "\nTotal: {}".format(len(queryset))
    return HttpResponse(response)


@login_required
def list_my(request):
    response = ""
    queryset = resourceInfoType_model.objects.filter(owners__in=[request.user], storage_object__deleted=False)
    for q in queryset:
        response += u"{}\t{}\t{}\n".format(
            q.id,
            best_lang_value_retriever(q.identificationInfo.resourceName),
            publication_status.get(q.storage_object.publication_status))

    response += "\nTotal: {}".format(len(queryset))
    return HttpResponse(response)
