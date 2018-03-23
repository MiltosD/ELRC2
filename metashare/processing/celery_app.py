from __future__ import absolute_import
import os
from metashare import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metashare.settings")

from celery import Celery

app = Celery('processing',
             broker='amqp://{}:{}@192.168.188.113'.format(settings.RABBIT_USER, settings.RABBIT_PASS),)

app.config_from_object('django.conf:settings')

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Optional configuration, see the application user guide.
app.conf.update(
    CELERY_TIMEZONE='Europe/Athens',
    # CELERYD_CONCURRENCY = 4,
    CELERY_TASK_RESULT_EXPIRES=3600,
    CELERY_TASK_IGNORE_RESULT=False,
    CELERY_ACCEPT_CONTENT=['json', 'msgpack', 'yaml'],
    CELERY_TASK_SERIALIZER='json',
    CELERY_RESULT_SERIALIZER='json',
    CELERYD_FORCE_EXECV=True,
    CELERY_SEND_TASK_ERROR_EMAILS=True,
    ADMINS=(
        ('Miltos Deligiannis', 'mdel@ilsp.gr'),
    ),
    CELERY_IMPORTS=("metashare.processing.tasks",),
    SERVER_EMAIL='no-reply@elrc-share.eu',
    EMAIL_USE_TLS=True,
    EMAIL_HOST='smtp.live.com',
    EMAIL_PORT=587,
    EMAIL_HOST_USER='mdel@windowslive.com',
    EMAIL_HOST_PASSWORD='a2s9ap123',
)

if __name__ == '__main__':
    app.start()
