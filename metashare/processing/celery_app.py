from __future__ import absolute_import
import os
from metashare import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metashare.settings")

from celery import Celery

app = Celery('processing',
             broker='amqp://{}:{}@{}'.format(settings.RABBIT_USER, settings.RABBIT_PASS, settings.CAMEL_IP),
             backend='rpc://{}:{}@{}'.format(settings.RABBIT_USER, settings.RABBIT_PASS, settings.CAMEL_IP),)

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
    CELERYD_TASK_TIME_LIMIT=3600,
    CELERY_SEND_TASK_ERROR_EMAILS=True,
    ADMINS=(
        ('Miltos Deligiannis', 'mdel@ilsp.gr'),
    ),
    CELERY_IMPORTS=("metashare.processing.tasks",),
    SERVER_EMAIL='no-reply@elrc-share.eu',
    EMAIL_USE_TLS=True,
    EMAIL_HOST=settings.EMAIL_HOST,
    EMAIL_PORT=settings.EMAIL_PORT,
    EMAIL_HOST_USER=settings.EMAIL_HOST_USER
)

if __name__ == '__main__':
    app.start()
