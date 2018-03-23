# -*- coding: utf-8 -*-
from __future__ import absolute_import, division

import logging
from celery import shared_task
from django.core.mail import send_mail
from metashare.processing.celery_app import app
from metashare.settings import CAMEL_IP

# Setup logging support.
LOGGER = logging.getLogger(__name__)


@app.task(name='loop', ignore_result=False)
def test_celery(num):
    j = 0
    for i in range(num):
        j += i
    if j == 4950:
        send_mail("Task Success", "Task successfull: {}".format(j), "mdel@windowslive.com", ["mdel@ilsp.gr"],
                  fail_silently=False)
    else:
        send_mail("Task Fail", "Task failed: {}".format(j), "mdel@windowslive.com", ["mdel@ilsp.gr"],
                  fail_silently=False)
    return j == 4950


@app.task(name="process_new")
def process_new(input_id, zipfile, service_id):
    camel_url = "http://{}/ILSP/elrc/{}/{}!{}/{}/".format(CAMEL_IP, input_id, input_id, zipfile, service_id)
    return camel_url
