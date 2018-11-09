# -*- coding: utf-8 -*-
from __future__ import absolute_import, division

import json
import logging
import time
import urllib2
from shutil import copyfile

import os
import requests
from celery import states
from celery.exceptions import Ignore
from django.contrib.auth.models import User
from django.core.mail import send_mail
from metashare.processing.celery_app import app
from metashare.processing.models import Processing
from metashare.repository.models import resourceInfoType_model
from metashare.settings import CAMEL_IP, CAMEL_PORT, UNITTESTING, MONITOR_TASK_IP, DJANGO_URL, PROCESSING_INPUT_PATH

# Setup logging support.
LOGGER = logging.getLogger(__name__)

from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

MONITOR_SLEEP = 6


def _call_camel(input_id, zipfile, service_id):
    # Construct the request
    # e.g http://elrc2-services.ilsp.gr:8888/ILSP/elrc/12345/12345!archive.zip/2/
    camel_url = "http://{}:{}/ILSP/elrc/{}/{}!{}/{}/".format(CAMEL_IP, CAMEL_PORT, input_id, input_id, zipfile,
                                                             service_id)
    if not UNITTESTING:
        try:
            response = urllib2.urlopen(camel_url)
            html = response.read()
        except Exception, exc:
            LOGGER.error(exc, exc_info=True)


def _parse_monitor_content(content):
    span = 2
    content_split = content.split(":")
    temp_list = [":".join(content_split[i:i + span]) for i in range(1, len(content_split), span)]
    result_dict = dict()
    for i in temp_list:
        # get k, v
        item = i.split(":")
        k = item[0].strip()
        # try to convert numeric strings to ints
        try:
            v = int(item[1].strip())
        except ValueError:
            # next try to parse booleans
            try:
                v = json.loads(item[1].strip().lower())
            except ValueError:
                v = item[1].strip()
        result_dict[item[0].strip()] = v
    return result_dict


@app.task(name='loop', ignore_result=False, bind=True)
def test_celery(self, num):
    j = 0
    for i in range(num):
        j += i
    if j == 4950:
        return True
    else:
        self.update_state(state=states.FAILURE)

        # ignore the task so no other state is recorded
        raise Ignore()


def _monitor_processing(input_id, resource_object=None):
    monitor = requests.get("{}{}".format(MONITOR_TASK_IP, input_id))
    monitor_dict = _parse_monitor_content(monitor.content)
    if resource_object:
        monitor_dict.update(resource={"id": resource_object.id, "name": resource_object})
    return monitor_dict


def monitor_processing(processing_object, resource_object=None):
    time.sleep(2)
    monitor = _monitor_processing(processing_object.job_uuid, resource_object)
    # check if the dataset zip is extracted successfully
    if monitor['archiveExtrSuccesfully'] == 1:
        processing_object.status = "progress"
        processing_object.save()
        while monitor['SuccesfullyProcessed'] == 0 and monitor['Errors'] == 0:
            monitor = _monitor_processing(processing_object.job_uuid, resource_object)
            time.sleep(MONITOR_SLEEP)

        while monitor['SuccesfullyProcessed'] + monitor['Errors'] < monitor['Total']:
            monitor = _monitor_processing(processing_object.job_uuid, resource_object)
            time.sleep(MONITOR_SLEEP)

        if monitor['SuccesfullyProcessed'] == monitor['Total']:
            processing_object.status = "successful"
        elif monitor['Errors'] == monitor['Total']:
            processing_object.status = "failed"
        elif monitor['SuccesfullyProcessed'] + monitor['Errors'] == monitor['Total']:
            processing_object.status = "partial"
    else:
        processing_object.status = 'failed'
    processing_object.save()
    return processing_object.status


@app.task(name='send-failure-mail', ignore_result=False, bind=True)
def send_failure_mail(self, processing_id):
    processing_object = Processing.objects.get(job_uuid=processing_id)
    # deactivate the object
    processing_object.active = False
    processing_object.save()
    resource = None
    # init email
    email_subject = "[ELRC-SHARE] Processing Result Failed"
    # if processing object source is elrc resource get the name
    if processing_object and processing_object.elrc_resource:
        resource = processing_object.elrc_resource
    email_body = "Dear {},\n\nYour processing request for '{}', (id: {}), {} has not been completed.\n" \
                 "Please check that your data files are in the processable formats \n" \
                 "and the zip archive does not contain subdirectories.\n\n" \
                 "The ELRC-SHARE Team".format(processing_object.user.username, processing_object.service,
                                              processing_id, "on '{}'".format(resource) if resource else '')
    sender = "no-reply@elrc-share.eu"
    to = [processing_object.user.email]
    logger.info("Sending Failure email to {}".format(processing_object.user.username))
    send_mail(email_subject, email_body, sender, to, fail_silently=False)
    return True


@app.task(name='build-link', ignore_result=False, bind=True)
def build_link(self, processing_id):
    processing_object = Processing.objects.get(job_uuid=processing_id)
    resource = None
    data_link = "{}/repository/processing/download/{}/".format(DJANGO_URL, processing_id)

    # init email
    email_subject = "[ELRC-SHARE] Processing Result {}"
    # if processing object source is elrc resource get the name
    if processing_object and processing_object.elrc_resource:
        resource = processing_object.elrc_resource
    email_body = "Dear {},\n\nYour processing request for '{}', (id: {}), {} has {}.\n" \
                 "You can download the result of your request, within two (2) days, by clicking " \
                 "on the following link:\n\n" \
                 "{}\n\nPlease note that after 2 days your processing results will be deleted and " \
                 "the above link will become inactive.\n\n" \
                 "Thank you for using the ELRC-SHARE services\n\n" \
                 "The ELRC-SHARE Team"
    sender = "no-reply@elrc-share.eu"
    to = [processing_object.user.email]
    if processing_object.status == "successful":
        email_subject = email_subject.format('Successful')
        email_body = email_body.format(processing_object.user.username, processing_object.service,
                                       processing_id, "on '{}'".format(resource) if resource else '',
                                       "been completed successfully",
                                       data_link)
    else:
        email_subject = email_subject.format('Partially Successful')
        email_body = email_body.format(processing_object.user.username,
                                       processing_object.service,
                                       processing_id, "on '{}'".format(resource) if resource else '',
                                       "been partially completed",
                                       data_link)
    logger.info("Sending Success email to {}".format(processing_object.user.username))
    send_mail(email_subject, email_body, sender, to, fail_silently=False)
    return True


@app.task(name="process-new", ignore_result=False, bind=True)
def process_new(self, service_name, input_id, zipfile, service_id, user_id):
    # make the request to camel and create a new Processing object in 'PENDING' status
    logger.info("Calling Camel for request {}".format(input_id))
    _call_camel(input_id, zipfile, service_id)
    logger.info("Creating Processing object with id {}".format(input_id))
    processing_object = Processing.objects.create(
        source='user_upload',
        service=service_name,
        user=User.objects.get(id=user_id),
        job_uuid=input_id,
        status="pending",
        active=True
    )
    monitor = monitor_processing(processing_object)
    if monitor == 'failed':
        self.update_state(state=states.FAILURE)
        logger.error("Task with id {} has failed".format(input_id))
        raise Ignore()
    else:
        return True


@app.task(name="process-existing", ignore_result=False, bind=True)
def process_existing(self, resource_id, service_name, input_id, service_id, user_id):
    resource_object = resourceInfoType_model.objects.get(id=resource_id)
    file_src = resource_object.storage_object.get_download()
    file_dest = "{}/{}".format(PROCESSING_INPUT_PATH, input_id)

    # create directory
    try:
        if not os.path.isdir(file_dest):
            os.makedirs(file_dest)
    except:
        raise OSError, "Could not write to processing input path"

    logger.info("Copying File to {}".format(file_dest))
    copyfile(file_src, '{}/{}'.format(file_dest, "archive.zip"))

    logger.info("Calling Camel for request {}".format(input_id))
    _call_camel(input_id, "archive.zip", service_id)

    logger.info("Creating Processing object with id {}".format(input_id))
    processing_object = Processing.objects.create(
        source='elrc_resource',
        elrc_resource=resource_object,
        service=service_name,
        user=User.objects.get(id=user_id),
        job_uuid=input_id,
        status="pending",
        active=True
    )
    monitor = monitor_processing(processing_object, resource_object)
    if monitor == 'failed':
        self.update_state(state=states.FAILURE)
        logger.error("Task with id {} has failed".format(input_id))
        raise Ignore()
    else:
        return True
