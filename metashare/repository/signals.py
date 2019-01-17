from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver

from haystack.exceptions import NotHandled
from haystack.signals import BaseSignalProcessor

from metashare.storage.models import StorageObject, INGESTED, PUBLISHED
from metashare.repository.models import resourceInfoType_model
from project_management.models import ManagementObject


class PatchedSignalProcessor(BaseSignalProcessor):
    """
    A patched haystack signal processor. Send signal to update
    haystack resourceInfoType_modelIndex when the StorageObject instance
    gets saved and the resourceInfoType_model gets deleted.
    """

    def setup(self):
        """
        Register the ``StorageOject`` model post_save signal
        and the ``resourceInfoType_model`` model post_delete signal.
        """
        models.signals.post_save.connect(self.handle_save,
                                         sender=StorageObject)

        models.signals.post_delete.connect(self.handle_delete,
                                           sender=resourceInfoType_model)

    def teardown(self):
        """
        Unregister the ``StorageOject`` model post_save signal
        and the ``resourceInfoType_model`` model post_delete signal.
        """
        models.signals.post_save.disconnect(self.handle_save,
                                            sender=StorageObject)

        models.signals.post_delete.disconnect(self.handle_delete,
                                              sender=resourceInfoType_model)

    def handle_save(self, sender, instance, **kwargs):
        """
        Given a StorageObject model instance, determine which backends the
        update should be sent to & update the object on those backends.
        """
        # only create/update index entries of ingested and published resources
        if instance.publication_status in (INGESTED, PUBLISHED):
            using_backends = self.connection_router.for_write(instance=instance)

            for using in using_backends:
                try:
                    index = self.connections[using].get_unified_index() \
                        .get_index(resourceInfoType_model)
                    index.update_object(instance, using=using)
                except NotHandled:
                    # TODO: Maybe log it or let the exception bubble?
                    pass


# PROJECT MANAGEMENT
@receiver(post_save, sender=resourceInfoType_model)
def create_management_object(sender, instance, created, **kwargs):
    try:
        mo = ManagementObject.objects.get(resource=instance)
        mo.save()
    except ObjectDoesNotExist:
        mo = ManagementObject.objects.create(resource=instance, id=instance.id)
        # save again to set partner
        mo.save()


@receiver(pre_delete, sender=resourceInfoType_model)
def delete_management_object(sender, instance, **kwargs):
    try:
        mng_obj = ManagementObject.objects.get(resource=instance)
        mng_obj.delete()
    except ObjectDoesNotExist:
        pass
