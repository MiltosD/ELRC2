from metashare.repository.templatetags.is_member import is_member
from metashare.settings import REST_API_KEY
from tastypie.authentication import Authentication
from tastypie.authorization import DjangoAuthorization
from tastypie.compat import get_module_name
from tastypie.exceptions import Unauthorized
from tastypie.http import HttpUnauthorized


class RepositoryApiKeyAuthentication(Authentication):
    def _unauthorized(self):
        return HttpUnauthorized()

    def is_authenticated(self, request, **kwargs):

        # superusers and anyone with permission does not need to define an API key
        if request.user.is_superuser or request.user.has_perm('auth.access_api'):
            return True
        # Check for api key if the user is not logged in the repository (e.g. cURL, etc)
        # First check if the key is in the "auth" param
        elif request.GET.get('auth'):
            api_key = request.GET.get('auth').strip()
        # Next check if the key is in the request header
        elif request.META.get('HTTP_AUTHORIZATION'):
            api_key = request.META['HTTP_AUTHORIZATION'].strip()
        # if all above fails, the user is unauthorized
        else:
            return self._unauthorized()

        key_auth_check = self.get_key(api_key)
        return key_auth_check

    def get_key(self, api_key):
        if api_key != REST_API_KEY.strip():
            return self._unauthorized()
        return True


class EditorAPiAuthentication(RepositoryApiKeyAuthentication):
    def is_authenticated(self, request, **kwargs):

        # superusers and anyone with permission does not need to define an API key
        if request.user.is_superuser or request.user.has_perm('auth.can_access_editor_api'):
            return True
        else:
            return self._unauthorized()


class EditorUserAuthorization(DjangoAuthorization):
    """
    Uses permission checking from ``django.contrib.auth`` to map
    ``POST / PUT / DELETE / PATCH`` to their equivalent Django auth
    permissions.

    Both the list & detail variants simply check the model they're based
    on, as that's all the more granular Django's permission setup gets.
    This extension includes resource ownership in order to decide whether
    a resource can be updated by the logged in user
    """

    # By default, following `ModelAdmin` "convention", `app.change_model` is used
    # `django.contrib.auth.models.Permission` as perm code for viewing and updating.
    # https://docs.djangoproject.com/es/1.9/topics/auth/default/#permissions-and-authorization
    READ_PERM_CODE = 'change'

    def base_checks(self, request, model_klass):
        # If it doesn't look like a model, we can't check permissions.
        if not model_klass or not getattr(model_klass, '_meta', None):
            return False

        # User must be logged in to check permissions.
        if not hasattr(request, 'user'):
            return False

        return model_klass

    def check_user_perm(self, user, permission, obj_or_list):
        return user.has_perm(permission)

    def perm_list_checks(self, request, code, obj_list):
        klass = self.base_checks(request, obj_list.model)
        if klass is False:
            return []

        permission = '%s.%s_%s' % (
            klass._meta.app_label,
            code,
            get_module_name(klass._meta)
        )

        if self.check_user_perm(request.user, permission, obj_list):
            if get_module_name(klass._meta) is "resourceinfotype_model" and not \
                    (is_member(request.user, 'ecmembers') or is_member(request.user, 'elrcReviewers')
                     or request.user.is_superuser):
                return obj_list.filter(owners__in=[request.user])
            else:
                return obj_list

        return obj_list.none()

    def perm_obj_checks(self, request, code, obj):
        klass = self.base_checks(request, obj.__class__)
        if klass is False:
            raise Unauthorized("You are not allowed to access that resource.")

        permission = '%s.%s_%s' % (
            klass._meta.app_label,
            code,
            get_module_name(klass._meta)
        )

        # Additional check: The logged in user owns the resource
        if self.check_user_perm(request.user, permission, obj):
            if request.method == 'GET':
                if get_module_name(klass._meta) is 'resourceinfotype_model' \
                        and (request.user.is_superuser or is_member(request.user, 'elrcReviewers') or \
                                     (is_member(request.user,
                                                'ecmembers') and obj.storage_object.publication_status != 'i')
                             or request.user in obj.owners.all()):
                    return True
                else:
                    return False
            elif request.method == 'PATCH':
                if get_module_name(klass._meta) is 'resourceinfotype_model' \
                        and (request.user.is_superuser or is_member(request.user, 'elrcReviewers') or \
                             request.user in obj.owners.all()):
                    return True
                else:
                    return False
            return True

        raise Unauthorized("You are not allowed to access that resource.")

    def read_list(self, object_list, bundle):
        return self.perm_list_checks(bundle.request, self.READ_PERM_CODE, object_list)

    def read_detail(self, object_list, bundle):
        return self.perm_obj_checks(bundle.request, self.READ_PERM_CODE, bundle.obj)

    def create_list(self, object_list, bundle):
        return self.perm_list_checks(bundle.request, 'add', object_list)

    def create_detail(self, object_list, bundle):
        return self.perm_obj_checks(bundle.request, 'add', bundle.obj)

    def update_list(self, object_list, bundle):
        return self.perm_list_checks(bundle.request, 'change', object_list)

    def update_detail(self, object_list, bundle):
        return self.perm_obj_checks(bundle.request, 'change', bundle.obj)

    def delete_list(self, object_list, bundle):
        return self.perm_list_checks(bundle.request, 'delete', object_list)

    def delete_detail(self, object_list, bundle):
        return self.perm_obj_checks(bundle.request, 'delete', bundle.obj)
