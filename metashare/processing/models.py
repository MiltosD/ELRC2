import datetime
import logging

from django.db import models
from django.contrib.auth.models import User

from metashare.repository.models import resourceInfoType_model
from metashare.repository.templatetags.is_member import is_member as member
from metashare.settings import PROCESSING_RETENTION_DAYS
from metashare.settings import LOG_HANDLER

try:
    from django.utils.timezone import now as datetime_now
except ImportError:
    datetime_now = datetime.datetime.now

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)


class ProcessingManager(models.Manager):
    def delete_expired_processings(self):
        """
        Remove expired instances of ``Processing`` and mark as deleted
        their associated primary and derived LRs.

        Processings to be deleted are identified by searching for
        instances of ``Processing`` with expired activation
        keys (activated to be False). Processings that have a user,
        who remains simple (i.e not a member) after the expiration date
        will be deleted.

        It is recommended that this method be executed regularly as
        part of your routine site maintenance; this application
        provides a custom management command which will call this
        method, accessible as ``manage.py cleanup_processings``.
        """
        for processing in self.filter(active=False):
            try:
                if processing.activation_expired():
                    processing_pk = processing.pk
                    # TODO: Delete data from disk
                    LOGGER.info(u"Processing {} is deleted.".format(processing_pk))
            except resourceInfoType_model.DoesNotExist:
                # delete the processing object
                processing_pk = processing.pk
                processing.delete()
                LOGGER.info(u"Processing {} is deleted.".format(processing_pk))


STATUS_CHOICES = (
    ('pending', 'PENDING'),
    ('progress', 'IN PROGRESS'),
    ('partial', 'PARTIALLY SUCCESSFUL'),
    ('successful', 'SUCCESSFUL'),
    ('failed', 'FAILED'),
    ('canceled', 'CANCELED')
)


class Processing(models.Model):
    """
    Processing model: Stores info about the processing
    """
    # Where the data to be processed came from
    source = models.CharField(verbose_name="Data Source",
                              choices=(("elrc_resource", "ELRC Resource"), ("user_upload", "User Upload")),
                              max_length=13)

    service = models.CharField(verbose_name='Processing Service', max_length=30, blank=True)

    elrc_resource = models.ForeignKey(resourceInfoType_model,
                                         verbose_name="ELRC Resource",
                                         related_name='processing_resources', blank=True, null=True)
    # derived_resource = models.OneToOneField(resourceInfoType_model, null=True)
    # services = models.ManyToManyField(resourceInfoType_model,
    #                                   related_name='processing_services')
    user = models.ForeignKey(User, verbose_name="User", null=True, related_name='processing_services')
    date_created = models.DateTimeField(verbose_name="Creation Date", auto_now=False, auto_now_add=True)
    job_uuid = models.CharField(verbose_name="Processing Job UUID", max_length=32)
    status = models.CharField(verbose_name="Processing Status",
                              choices=STATUS_CHOICES,
                              max_length=10,
                              null=True, blank=True)
    active = models.NullBooleanField(verbose_name="Active", null=True)

    objects = ProcessingManager()

    def __unicode__(self):
        _unicode = u'{}/{} (id: "{}")'.format(self.user, self.job_uuid, self.id)
        return _unicode

    def activation_expired(self):
        """
        Determine whether this ``Processing``'s activation
        has expired, returning a boolean -- ``True`` if the key
        has expired.
        
        Key expiration is determined by a two-step process:
        
        1. If the processing has already been activated, the key
           will have been reset to ``True``. Re-activating
           is not permitted, and so this method returns ``True`` in
           this case.

        2. Otherwise, the date the processing created is incremented by
           the number of days specified in the setting
           ``PROCESSING_ACTIVATION_DAYS`` (which should be the number of
           days after the processing creation during which a user is allowed to
           apply to be a member of an editor group); if the result is less than or
           equal to the current date, the key has expired and this
           method returns ``True``.
        
        """
        is_active = self.get_activation()
        expiration_date = datetime.timedelta(days=PROCESSING_RETENTION_DAYS)
        return not is_active and \
               (self.date_created + expiration_date <= datetime_now())

    # ===========================================================================
    # activation_expired.boolean = True
    # ===========================================================================

    def get_activation(self):
        """
        Make it active if the user became editor or organizer or superuser
        i.e has manager permissions
        """
        # in the case that the processing is inactive we have only
        # one user for this processing
        user = self.user
        is_member = user.is_superuser or member(user, 'ecmembers')
        if self.activated:
            return True
        elif not self.activated and is_member:
            # if the user in the meantime got manager permissions
            # make the processing object instance active
            self.activated = True
            self.save()
            return True
        else:
            return False
