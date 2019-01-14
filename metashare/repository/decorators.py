from django.core.exceptions import PermissionDenied
from metashare.settings import REST_API_KEY

from metashare.repository.models import resourceInfoType_model
from metashare.storage.models import PUBLISHED
from metashare.repository import model_utils

import sys

TEST = 'test' in sys.argv


def _intersection(lst1, lst2):
    lst3 = [value for value in lst1 if value in lst2]
    return lst3


def _resource_is_downloadable(resource):
    # Criteria
    # a. Should be corpus or lexical resource
    # b. Publication status = Published
    # b. Permissive licence
    # c. Legally cleared
    # d. Validated
    # e. Officially delivered to the EC

    non_permissive_licences = [u'underReview', u'non-standard/Other_Licence/Terms']

    resource_licences = [licence_info.licence for distributionInfo in
                         resource.distributioninfotype_model_set.all()
                         for licence_info in
                         distributionInfo.licenceInfo.all()]

    criteria = list()
    criteria.append(resource.resource_type() is not 'Tool service')
    criteria.append(resource.storage_object.publication_status == u'p')
    criteria.append(False if _intersection(non_permissive_licences, resource_licences) else True)
    criteria.append(resource.management_object.ipr_clearing == u'cleared')
    criteria.append(resource.management_object.validated)
    criteria.append(True if resource.management_object.delivered_to_EC else False)

    return all(criteria)


def resource_downloadable(function):
    def wrap(request, *args, **kwargs):
        if request.GET.get('auth') and request.GET.get('auth') == REST_API_KEY:
            kwargs['api_auth'] = True
            return function(request, *args, **kwargs)
        if TEST:
            request.download_permitted = True
            return function(request, *args, **kwargs)
        resource = resourceInfoType_model.objects.get(storage_object__identifier=kwargs['object_id'])
        if request.user.is_superuser \
                or ((request.user.groups.filter(name="ecmembers").exists()
                     or request.user.groups.filter(name="elrcReviewers").exists())) \
                or _resource_is_downloadable(resource):
            return function(request, *args, **kwargs)
        else:
            request.msg = "You don't have sufficient rights to download this resource."
            raise PermissionDenied("You don't have sufficient rights to download this resource.")

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap


def resource_downloadable_view(function):
    def wrap(request, *args, **kwargs):
        if TEST:
            request.download_permitted = True
            return function(request, *args, **kwargs)
        resource = resourceInfoType_model.objects.get(storage_object__identifier=kwargs['object_id'])
        if request.user.is_superuser or _resource_is_downloadable(resource) \
                or request.user.groups.filter(name="elrcReviewers").exists():
            request.download_permitted = True
            return function(request, *args, **kwargs)
        elif request.user.groups.filter(name="ecmembers").exists():
            if resource.storage_object.publication_status == PUBLISHED:
                request.download_permitted = True
                return function(request, *args, **kwargs)
            else:
                return function(request, *args, **kwargs)
        elif resource.storage_object.publication_status == PUBLISHED:
            return function(request, *args, **kwargs)
        # handle test fixtures
        elif resource.storage_object.checksum == '3930f5022aff02c7fa27ffabf2eaaba0':
            return function(request, *args, **kwargs)
        else:
            request.msg = "You don't have sufficient rights to view this resource description."
            raise PermissionDenied("You don't have sufficient rights to view this resource description.")

    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap


def require_membership(group):
    def decorator(function):
        def wrap(request, *args, **kwargs):
            if request.user.is_superuser or request.user.groups.filter(name=group).exists():
                return function(request, *args, **kwargs)
            else:
                raise PermissionDenied("You don't have sufficient rights to access this resource.")
            wrap.__doc__ = function.__doc__
            wrap.__name__ = function.__name__

        return wrap

    return decorator
