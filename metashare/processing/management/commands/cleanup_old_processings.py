import time
from shutil import rmtree

import os
from django.core.management import BaseCommand
from metashare.local_settings import PROCESSING_INPUT_PATH, PROCESSING_OUTPUT_PATH
from metashare.processing.models import Processing


class Command(BaseCommand):
    """
    Removes files from the passed in path that are older than or equal
    to the number_of_days
    """

    def _cleanup_dir(self, dir_path, directory, identifier):
        full_path = os.path.join(dir_path, directory)
        print identifier, full_path
        try:
            processing_object = Processing.objects.get(job_uuid=identifier)
            if processing_object.activation_expired():
                rmtree(full_path)
                processing_object.active = False
                processing_object.save()
        except Processing.DoesNotExist:
            pass

    def handle(self, *args, **options):
        for d in os.listdir(PROCESSING_INPUT_PATH):
            print d
            self._cleanup_dir(PROCESSING_INPUT_PATH, d, identifier=d)
        for d in os.listdir(PROCESSING_OUTPUT_PATH):
            identifier = d[:-3]
            self._cleanup_dir(PROCESSING_OUTPUT_PATH, d, identifier=identifier)
