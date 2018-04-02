import json as json
import logging
from mimetypes import guess_type
from uuid import uuid4
from zipfile import BadZipfile

import os
import xmltodict
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from metashare.processing.models import Processing
from metashare.processing.tasks import process_new, _monitor_processing, send_failure_mail, build_link, process_existing
from metashare.repository.decorators import require_membership
from metashare.repository.model_utils import is_processable
from metashare.repository.models import resourceInfoType_model
from metashare.settings import LOG_HANDLER, ROOT_PATH, PROCESSING_INPUT_PATH, PROCESSING_MAXIMUM_UPLOAD_SIZE, \
    PROCESSING_OUTPUT_PATH
from os.path import split, getsize

MAXIMUM_READ_BLOCK_SIZE = 4096

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)


def _get_service_by_id(available_services, s_id):
    for service in available_services['service']:
        if service['id'] == s_id:
            return service


def _check_processability(resource):
    if is_processable(resource)[0] == "YES":
        return True
    return False


@require_membership("ecmembers")
def process_repo_resource(request, resource_id):
    xml = open("{}/processing/services-ELRC.xml".format(ROOT_PATH), 'r').read()
    available_services = json.loads(json.dumps(xmltodict.parse(xml, encoding='utf-8')).replace("@", "")
                                    .replace("#", ""))['services']

    resource = resourceInfoType_model.objects.get(id=resource_id)

    input_id = '{}'.format(uuid4().hex)

    if request.method == "POST":
        response = dict()
        # !IMPORANT
        # Check again if the resource is processable, since the user may input the
        # resource id directly in to the url, bypassing first check
        if not _check_processability(resource):
            response['status'] = "alert alert-danger"
            response['message'] = "This resource is not processable"
            return JsonResponse({'info': available_services, 'msg': response})

        service_id = request.POST['service_select']
        selected_service = _get_service_by_id(available_services, service_id)
        response['status'] = "alert alert-success"
        response['message'] = "Your processing request (id: {}) has been submitted. As soon as the process is " \
                              "completed, you will be notified via email about the status of your request.".format(
            input_id)
        process_existing.delay(resource_id, selected_service['name'], input_id, service_id, request.user.id)

        return JsonResponse({'info': available_services, 'msg': response})

    available_services['resource'] = {
        "id": resource.id,
        "name": resource
    }

    # !IMPORANT
    # Check again if the resource is processable, since the user may input the
    # resource id directly in to the url, bypassing first check. Disable form if
    # the resource is not processable
    if not _check_processability(resource):
        response = dict()
        response['status'] = "alert alert-danger"
        response['message'] = "This resource is not processable"
        response['disable_form'] = True
        return render_to_response('repository/processing/services.html',
                                  {'info': available_services, 'msg': response},
                                  context_instance=RequestContext(request))
    return render_to_response('repository/processing/services.html',
                              {'info': available_services},
                              context_instance=RequestContext(request))


@login_required
@require_membership("ecmembers")
def services(request):
    xml = open("{}/processing/services-ELRC.xml".format(ROOT_PATH), 'r').read()

    available_services = json.loads(json.dumps(xmltodict.parse(xml, encoding='utf-8')).replace("@", "")
                                    .replace("#", ""))['services']
    input_id = '{}'.format(uuid4().hex)
    zipped = "archive.zip"
    if request.method == "POST":
        print request.POST
        response = {}
        upload_to = "{}/{}".format(PROCESSING_INPUT_PATH, input_id)
        service_id = request.POST['service_select']
        selected_service = _get_service_by_id(available_services, service_id)
        if not request.FILES['zipfile'].size > PROCESSING_MAXIMUM_UPLOAD_SIZE:
            try:
                if not os.path.isdir(upload_to):
                    os.makedirs(upload_to)
            except:
                raise OSError, "Could not write to processing input path"
            destination = open('{}/{}'.format(upload_to, zipped), 'wb+')

            for chunk in request.FILES['zipfile'].chunks():
                destination.write(chunk)
            destination.close()
            import zipfile
            zfile_path = '{}/{}'.format(upload_to, zipped)
            try:
                zfile = zipfile.ZipFile(zfile_path)
            except BadZipfile:
                os.remove(zfile_path)
                os.rmdir(os.path.abspath(os.path.join(zfile_path, os.pardir)))
                response['status'] = "alert alert-warning"
                response['message'] = "Your request could not be completed. " \
                                      "The file you tried to upload is corrupted or it is not a valid '.zip' file. " \
                                      "Please make sure that you have compressed your data properly."
                return render_to_response('repository/processing/services.html', \
                                          {'info': available_services, 'msg': response},
                                          context_instance=RequestContext(request))
            zip_ok = True
            try:
                if zfile.testzip() is not None:
                    zip_ok = False
            except:
                zip_ok = False
            if not zipfile.is_zipfile(zfile_path) or \
                    not zip_ok or \
                    not str(request.FILES['zipfile']).endswith(".zip"):
                os.remove(zfile_path)
                os.rmdir(os.path.abspath(os.path.join(zfile_path, os.pardir)))
                response['status'] = "alert alert-warning"
                response['message'] = "Your request could not be completed. " \
                                      "The file you tried to upload is corrupted or it is not a valid '.zip' file. " \
                                      "Please make sure that you have compressed your data properly."
                return JsonResponse({'info': available_services, 'msg': response})

        else:
            response['status'] = "alert alert-warning"
            response['message'] = "The file you are trying to upload " \
                                  "is larger than the maximum upload file size ({:.10} MB)!".format(
                float(PROCESSING_MAXIMUM_UPLOAD_SIZE) / (1024 * 1024))
            return JsonResponse({'info': available_services, 'msg': response})
        response['status'] = "alert alert-success"
        response['message'] = "Your processing request (id: {}) has been submitted. As soon as the process is " \
                              "completed, you will be notified via email about the status of your request.".format(
            input_id)
        # task call
        process_new.delay(selected_service['name'], input_id, zipped, service_id, request.user.id)
        return JsonResponse({'info': available_services, 'msg': response})

    return render_to_response('repository/processing/services.html', \
                              {'info': available_services},
                              context_instance=RequestContext(request))


def get_data(request):
    """
    Get the new annotated data from the Text Processor
    """
    processing_id = request.GET.get('processing_id')
    data_file = request.GET.get('data_file')
    LOGGER.info(u'The data {} for the processing {} are delivered' \
                .format(data_file, processing_id))
    # get more info from monitor
    # TODO: get json response, not text
    monitor = _monitor_processing(processing_id)
    if monitor['Errors'] == monitor['Total'] or monitor['Completed'] != 1:
        send_failure_mail.delay(processing_id)
    else:
        build_link.delay(processing_id)
    return HttpResponse("Request received", status=200)


@login_required
@require_membership("ecmembers")
def download_processed_data(request, processing_id):
    dl_path = "{}/{}zip/archive.zip".format(PROCESSING_OUTPUT_PATH, processing_id)
    if dl_path:
        try:
            def dl_stream_generator():
                with open(dl_path, 'rb') as _local_data:
                    _chunk = _local_data.read(4096)
                    while _chunk:
                        yield _chunk
                        _chunk = _local_data.read(4096)

            # build HTTP response with a guessed mime type; the response
            # content is a stream of the download file
            filemimetype = guess_type(dl_path)[0] or "application/octet-stream"
            response = HttpResponse(dl_stream_generator(),
                                    content_type=filemimetype)
            response['Content-Length'] = getsize(dl_path)
            response['Content-Disposition'] = 'attachment; filename={0}' \
                .format(split(dl_path)[1])
            # LOGGER.info("Offering a local editor download of resource #{0}." \
            #             .format(object_id))
            return response
        except:
            raise Http404("The requested file does not exist or has been deleted.")


@login_required
@require_membership("ecmembers")
def my_processings(request):
    processings = Processing.objects.filter(user=request.user)
    result = list()
    for processing in processings:
        result.append({
            'processing_id': processing.id,
            'processing_request_id': processing.job_uuid,
            'service': processing.service,
            'data_source': processing.source,
            'elrc_resource': processing.elrc_resource,
            'submission_date': processing.date_created.strftime('%d/%m/%Y'),
            'status': processing.status,
            'link_active': processing.active
        })
    return render_to_response('repository/processing/user_processings.html',
                              {'processings': result},
                              context_instance=RequestContext(request))
