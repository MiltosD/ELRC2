import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse, HttpResponseBadRequest
from django.utils.encoding import smart_str

from metashare.repository.editor.resource_editor import ResourceModelAdmin
from metashare.repository.fields import best_lang_value_retriever
from metashare.repository.models import resourceInfoType_model
from metashare.repository.templatetags.is_member import is_member
from metashare.settings import LOG_HANDLER

admin = ResourceModelAdmin(model=resourceInfoType_model, admin_site=None)

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)

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
    if not resource:
        LOGGER.error(
            "Invalid API dataset download from user {}. Resource with id {} does not exist"
            .format(request.user, resource.id))
        return HttpResponseBadRequest()
    if resource and (request.user.is_superuser or request.user in resource.owners.all()
                     or is_member(request.user, 'elrcReviewers')):
        data = admin.datadl(request, object_id)
        LOGGER.info("Providing API dataset download for resource {} to user {}".format(resource.id, request.user))
        return data
    else:
        LOGGER.error("Unauthorized API dataset download for resource {} from user {}".format(resource.id, request.user))
        return HttpResponseForbidden()


def upload_data(request, object_id):
    """
    Provide direct resource dataset download form API
    :param request: request from API
    :param object_id: resource id to upload zip dataset to
    """

    resource = resourceInfoType_model.objects.get(pk=object_id)
    if resource and (request.user.is_superuser or request.user in resource.owners.all()):
        LOGGER.info("Providing API dataset upload for resource {} to user {}".format(resource.id, request.user))
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
        LOGGER.error("Unauthorized API dataset upload for resource {} from user {}".format(resource.id, request.user))
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
        LOGGER.info("Providing API XML export for resource {} to user {}".format(object_id, request.user))

        return admin.exportxml(request, object_id)
    else:
        LOGGER.error("Invalid API for XML export for resource {} from user {}".format(object_id, request.user))
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
    LOGGER.info("Providing API resource list to user {}".format(request.user))
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
    LOGGER.info("Providing API user resource list to user {}".format(request.user))
    return HttpResponse(response)
