from django.conf.urls import url
from django.contrib.admin.options import get_content_type_for_model
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.encoding import force_text
from django.db.models import Q
from haystack.query import SearchQuerySet
from metashare.repository import models as lr
from metashare.repository.api import validators
from metashare.repository.api.auth import RepositoryApiKeyAuthentication, EditorUserAuthorization
from metashare.repository.api.haystack_filters import encode_filter
from metashare.repository.models import documentInfoType_model, \
    documentUnstructuredString_model, corpusInfoType_model, lexicalConceptualResourceInfoType_model, \
    languageDescriptionInfoType_model, toolServiceInfoType_model
from metashare.repository.templatetags.is_member import is_member
from metashare.settings import DJANGO_URL
from metashare.storage.models import StorageObject
from project_management import models as pm
from tastypie import fields
from tastypie.authentication import Authentication
from tastypie.authorization import Authorization
from tastypie.constants import ALL_WITH_RELATIONS, ALL
from tastypie.exceptions import NotFound
from tastypie.paginator import Paginator
from tastypie.resources import ModelResource
from tastypie.utils import (
    dict_strip_unicode_keys, trailing_slash,
)

try:
    from django.db.models.fields.related import \
        SingleRelatedObjectDescriptor as ReverseOneToOneDescriptor
except ImportError:
    from django.db.models.fields.related_descriptors import \
        ReverseOneToOneDescriptor

EXCLUDES = ('copy_status', 'source_url')


def clean_bundle(bundle, root=None):
    if root:
        for f in bundle.data[root].keys():
            if not bundle.data[root][f]:
                del bundle.data[root][f]
    else:
        for f in bundle.data.keys():
            if not bundle.data[f]:
                del bundle.data[f]
    return bundle


def resolve_actor(related_bundle):
    if related_bundle.data.get('personInfo'):
        surname = related_bundle.data.get('personInfo').get('surname')
        given_name = related_bundle.data.get('personInfo').get('givenName')
        email = related_bundle.data.get('personInfo').get('communicationInfo').get('email')

        # If it is a create request, check if the object exists, in order to reuse it
        # If it is an update get the object by id, included in the bundle data
        rel = lr.personInfoType_model.objects.filter(
            surname=surname,
            communicationInfo__email=email).first()
        if rel:
            return rel
        else:
            rel = PersonResource()
            person_bundle = rel.save(
                rel.build_bundle(data=related_bundle.data.get('personInfo'))
            )
            # force some fields to be saved
            person_bundle.obj.surname = surname
            person_bundle.obj.givenName = given_name
            person_bundle.obj.save()
            return person_bundle.obj
    elif related_bundle.data.get('organizationInfo'):
        organizationName = related_bundle.data.get('organizationInfo').get('organizationName')
        organizationShortName = related_bundle.data.get('organizationInfo').get('organizationShortName')
        email = related_bundle.data.get('organizationInfo').get('communicationInfo').get('email')
        rel = lr.organizationInfoType_model.objects.filter(
            organizationName=organizationName).first()
        if rel:
            return rel
        else:
            rel = OrganizationResource()
            org_bundle = rel.save(
                rel.build_bundle(data=related_bundle.data.get('organizationInfo'))
            )
            # force some fields to be saved
            org_bundle.obj.organizationName = organizationName
            org_bundle.obj.organizationShortName = organizationShortName
            org_bundle.obj.save()
            return org_bundle.obj


class IdentificationResource(ModelResource):
    class Meta:
        queryset = lr.identificationInfoType_model.objects.all()
        authorization = Authorization()
        resource_name = 'identification'
        include_resource_uri = False
        validation = validators.ELRCValidation(model=queryset.model)

    resourceName = fields.DictField(attribute='resourceName')
    resourceShortName = fields.DictField(attribute='resourceShortName', null=True)
    description = fields.DictField(attribute='description')
    appropriatenessForDSI = fields.ListField(attribute='appropriatenessForDSI', null=True)
    identifier = fields.ListField(attribute='identifier', null=True)
    url = fields.ListField(attribute='url', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LicenceResource(ModelResource):
    class Meta:
        queryset = lr.licenceInfoType_model.objects.all()
        resource_name = "licence"
        authentication = RepositoryApiKeyAuthentication()
        authorization = Authorization()
        allowed_methods = ['get']
        include_resource_uri = False
        validation = validators.ELRCValidation(model=queryset.model)

    licence = fields.CharField(attribute='licence')
    otherLicenceName = fields.CharField(attribute='otherLicenceName', null=True)
    otherLicence_TermsText = fields.DictField(attribute='otherLicence_TermsText', null=True)
    otherLicence_TermsURL = fields.CharField(attribute='otherLicence_TermsURL', null=True)
    restrictionsOfUse = fields.ListField(attribute='restrictionsOfUse', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def obj_update(self, bundle, skip_errors=False, **kwargs):
        """
        A ORM-specific implementation of ``obj_update``.
        """
        bundle_detail_data = self.get_bundle_detail_data(bundle)
        arg_detail_data = kwargs.get(self._meta.detail_uri_name)
        if bundle_detail_data is None or (
                        arg_detail_data is not None and str(bundle_detail_data) != str(arg_detail_data)):
            try:
                lookup_kwargs = self.lookup_kwargs_with_identifiers(bundle, kwargs)
            except:
                # if there is trouble hydrating the data, fall back to just
                # using kwargs by itself (usually it only contains a "pk" key
                # and this will work fine.
                lookup_kwargs = kwargs

            try:
                bundle.obj = self.obj_get(bundle=bundle, **lookup_kwargs)
            except ObjectDoesNotExist:
                raise NotFound("A model instance matching the provided arguments could not be found.")

        bundle = self.full_hydrate(bundle)

        self.is_valid(bundle)

        if bundle.errors:
            return self.error_response(bundle.errors, bundle.request)

        return self.save(bundle, skip_errors=skip_errors)


class CommunicationResource(ModelResource):
    class Meta:
        queryset = lr.communicationInfoType_model.objects.all()
        resource_name = "communication"
        authorization = Authorization()
        include_resource_uri = False
        excludes = ['organizationinfotype_model', 'personinfotype_model']
        validation = validators.ELRCValidation(model=queryset.model)

    email = fields.ListField(attribute='email', blank=True)
    url = fields.ListField(attribute='url', null=True)
    address = fields.CharField(attribute='address', null=True)
    zipCode = fields.CharField(attribute='zipCode', null=True)
    city = fields.CharField(attribute='city', null=True)
    region = fields.CharField(attribute='region', null=True)
    country = fields.CharField(attribute='country', null=True)
    countryId = fields.CharField(attribute='countryId', null=True)
    telephoneNumber = fields.ListField(attribute='telephoneNumber', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ActorResource(ModelResource):
    class Meta:
        queryset = lr.actorInfoType_model.objects.all()
        resource_name = "actor"
        include_resource_uri = False
        authorization = Authorization()

    def dehydrate(self, bundle):
        instance_class = bundle.obj.as_subclass()
        if isinstance(instance_class, lr.personInfoType_model):
            bundle.data['personInfo'] = None
            person_res = PersonResource()
            person_bundle = person_res.build_bundle(obj=instance_class, request=bundle.request)
            bundle.data['personInfo'] = person_res.full_dehydrate(person_bundle).data
        elif isinstance(instance_class, lr.organizationInfoType_model):
            bundle.data['organizationInfo'] = None
            org_res = OrganizationResource()
            org_bundle = org_res.build_bundle(obj=instance_class, request=bundle.request)
            bundle.data['organizationInfo'] = org_res.full_dehydrate(org_bundle).data
        return clean_bundle(bundle)

    def save(self, bundle, skip_errors=False):
        if bundle.request.method == 'POST':
            if bundle.data.get('personInfo'):
                bundle.data = bundle.data.get('personInfo')
                person_res = PersonResource()
                person_bundle = person_res.save(
                    person_res.build_bundle(data=bundle.data, request=bundle.request)
                )
                for f in person_bundle.obj._meta.get_all_field_names():
                    if bundle.data.get(f) and not isinstance(getattr(person_bundle.obj, f),
                                                             lr.communicationInfoType_model):
                        setattr(person_bundle.obj, f, bundle.data[f])
                bundle.data = {}
                person_bundle.obj.save()
                bundle.obj.id = person_bundle.obj.id
                return super(ActorResource, self).save(bundle)
            elif bundle.data.get('organizationInfo'):
                bundle.data = bundle.data.get('organizationInfo')
                org_res = OrganizationResource()
                org_bundle = org_res.save(org_res.build_bundle(data=bundle.data, request=bundle.request))
                for f in org_bundle.obj._meta.get_all_field_names():
                    if bundle.data.get(f) and not isinstance(getattr(org_bundle.obj, f),
                                                             lr.communicationInfoType_model):
                        setattr(org_bundle.obj, f, bundle.data[f])
                bundle.data = {}
                org_bundle.obj.save()
                bundle.obj.id = org_bundle.obj.id
                return super(ActorResource, self).save(bundle)
        else:
            if bundle.data.get('personInfo'):
                try:
                    person = lr.personInfoType_model.objects.get(id=bundle.obj.id)
                    person.__dict__.update(bundle.data.get('personInfo'))
                    person.save()
                except lr.personInfoType_model.DoesNotExist:
                    person = resolve_actor(bundle)
                    person.__dict__.update(bundle.data.get('personInfo'))
                    person.save()
                    super(ActorResource, self).save(bundle)
            elif bundle.data.get('organizationInfo'):
                try:
                    org = lr.organizationInfoType_model.objects.get(id=bundle.obj.id)
                    org.__dict__.update(bundle.data.get('organizationInfo'))
                    org.save()
                except lr.organizationInfoType_model.DoesNotExist:
                    org = resolve_actor(bundle)
                    org.__dict__.update(bundle.data.get('organizationInfo'))
                    org.save()
                    super(ActorResource, self).save(bundle)


class OrganizationResource(ModelResource):
    class Meta:
        queryset = lr.organizationInfoType_model.objects.all()
        resource_name = "org"
        include_resource_uri = False
        authorization = Authorization()
        excludes = EXCLUDES
        always_return_data = True

    organizationName = fields.DictField(attribute='organizationName')
    organizationShortName = fields.DictField(attribute='organizationShortName', null=True)
    departmentName = fields.DictField(attribute='departmentName', null=True)
    communicationInfo = fields.ToOneField(CommunicationResource, 'communicationInfo', full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

        # def save(self, bundle, skip_errors=False):
        #     if bundle.obj:
        #         bundle.obj.communicationInfo.save()
        #     return super(OrganizationResource, self).save(bundle)


class PersonResource(ModelResource):
    class Meta:
        queryset = lr.personInfoType_model.objects.all()
        resource_name = "person"
        include_resource_uri = False
        authorization = Authorization()
        excludes = EXCLUDES

    surname = fields.DictField(attribute='surname')
    givenName = fields.DictField(attribute='givenName', null=True)
    sex = fields.CharField(attribute='sex', null=True)
    communicationInfo = fields.ToOneField(CommunicationResource, 'communicationInfo', full=True)
    position = fields.CharField(attribute='position', null=True)
    affiliation = fields.ToManyField(OrganizationResource, 'affiliation', null=True, full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []
                for related_bundle in bundle.data[field_name]:

                    # We expect only Organization m2m
                    rel = related_bundle.obj.__class__.objects.filter(
                        organizationName=related_bundle.obj.organizationName).first()
                    if rel:
                        related_objs.append(rel)
                    else:
                        rel = OrganizationResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        else:
            super(PersonResource, self).save_m2m(bundle)


class DistributionResource(ModelResource):
    class Meta:
        queryset = lr.distributionInfoType_model.objects.all()
        resource_name = "distribution"
        authorization = Authorization()
        include_resource_uri = False
        validation = validators.ELRCValidation(model=queryset.model)

    PSI = fields.BooleanField(attribute='PSI', null=True)
    licenceInfo = fields.ToManyField(LicenceResource, 'licenceInfo', full=True)  # Relation may change
    distributionMedium = fields.ListField(attribute='distributionMedium', null=True)
    downloadLocation = fields.ListField(attribute='downloadLocation', null=True)
    executionLocation = fields.ListField(attribute='executionLocation', null=True)
    attributionText = fields.DictField(attribute='attributionText', null=True)
    personalDataAdditionalInfo = fields.CharField(attribute='personalDataAdditionalInfo', null=True)
    sensitiveDataAdditionalInfo = fields.CharField(attribute='sensitiveDataAdditionalInfo', null=True)
    fee = fields.CharField(attribute='fee', null=True)
    iprHolder = fields.ToManyField(ActorResource, 'iprHolder', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []
                for related_bundle in bundle.data[field_name]:
                    if field_name == 'iprHolder':
                        related_objs.append(resolve_actor(related_bundle))
                    else:
                        # It is a licence. Create a new one
                        rel = LicenceResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        else:
            super(DistributionResource, self).save_m2m(bundle)


class MetadataInfoResource(ModelResource):
    class Meta:
        queryset = lr.metadataInfoType_model.objects.all()
        resource_name = "metadataInfo"
        allowed_methods = ['get', 'post']
        excludes = EXCLUDES
        include_resource_uri = False
        filtering = {
            'metadataCreationDate': ALL,
        }
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    metadataCreationDate = fields.DateField(attribute='metadataCreationDate', verbose_name='created')
    metadataCreator = fields.ToManyField(PersonResource, 'metadataCreator', full=True, null=True)
    metadataLanguageName = fields.ListField(attribute='metadataLanguageName')
    metadataLanguageId = fields.ListField(attribute='metadataLanguageId')
    metadataLastDateUpdated = fields.DateField(attribute='metadataLastDateUpdated', verbose_name='created', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []
                for related_bundle in bundle.data[field_name]:
                    # We expect only Person m2m
                    rel = lr.personInfoType_model.objects.filter(
                        surname=related_bundle.obj.surname,
                        communicationInfo__email=related_bundle.obj.communicationInfo.email).first()
                    if rel:
                        related_objs.append(rel)
                    else:
                        rel = PersonResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        else:
            super(MetadataInfoResource, self).save_m2m(bundle)


pub_status = dict(p='published', g='ingested', i='internal')


class StorageResource(ModelResource):
    class Meta:
        queryset = StorageObject.objects.all()
        resource_name = 'storage'
        allowed_methods = ['get']
        include_resource_uri = False
        authorization = Authorization()
        fields = ['identifier']

    def dehydrate(self, bundle):
        bundle.data['download_location'] = "{}/repository/download/{}".format(DJANGO_URL, bundle.obj.identifier)
        bundle.data['publication_status'] = pub_status.get(bundle.obj.publication_status)
        return clean_bundle(bundle)


class ManagementResource(ModelResource):
    class Meta:
        queryset = pm.ManagementObject.objects.all()
        resource_name = 'pm'
        include_resource_uri = False
        authorization = Authorization()

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LrResource(ModelResource):
    class Meta:
        queryset = lr.resourceInfoType_model.objects.filter(storage_object__deleted=False) \
            .exclude(storage_object__publication_status='i')
        allowed_methods = ['get']
        resource_name = 'lr'
        authentication = RepositoryApiKeyAuthentication()
        authorization = Authorization()
        ordering = ['metadataInfo']
        filtering = {
            'metadataInfo': ALL_WITH_RELATIONS
        }

    management = fields.ToOneField(ManagementResource, 'management_object', null=False, full=True)
    metadataInfo = fields.ToOneField(MetadataInfoResource, 'metadataInfo', null=True, full=True)
    identification = fields.ToOneField(IdentificationResource, 'identificationInfo', full=True)
    distribution = fields.ToManyField(DistributionResource, 'distributioninfotype_model_set', full=True)
    storage = fields.ToOneField(StorageResource, 'storage_object', full=True, null=True)

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/search%s$" % (self._meta.resource_name, trailing_slash()),
                self.wrap_view('get_search'), name="api_get_search"),
            url(r"^help", self.wrap_view('api_help'), name="api_help")
        ]

    def get_search(self, request, **kwargs):
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.dispatch_list(request)
        self.throttle_check(request)
        # Do the query.
        sqs = SearchQuerySet()
        query = request.GET.getlist("q")
        OR = request.GET.getlist("or")
        if query:
            for q in query:
                query_dict = {}
                encoded_q = encode_filter(q.split(':')[0], q.split(':')[1])
                try:
                    key = "{}Filter_exact".format(encoded_q.get('filter'))
                    value = encoded_q.get('value')
                    if ' ' in value:
                        key = key.replace('_', '__')
                    query_dict[key] = value
                    if OR:
                        sqs = sqs.filter_or(**query_dict)
                    else:
                        sqs = sqs.filter(**query_dict)
                except IndexError:
                    sqs = sqs.filter(content=q)
        # Apply tastypie filters if any whatsoever
        sqs_objects = [sq.object for sq in sqs]
        filtered = self.apply_filters(request, applicable_filters={})

        final_list = list(set(sqs_objects) & set(filtered))
        ids = [fl.id for fl in final_list]
        final_list = lr.resourceInfoType_model.objects.filter(id__in=ids)
        if 'latest' in request.GET.get('sort', ''):
            final_list = self.apply_sorting(final_list, options={'sort': [u'latest']})
        elif 'earliest' in request.GET.get('sort', ''):
            final_list = self.apply_sorting(final_list, options={'sort': [u'earliest']})

        paginator = Paginator(request.GET, final_list, resource_uri='/api/v1/lr/search/')

        to_be_serialized = paginator.page()

        bundles = [self.build_bundle(obj=result, request=request) for result in to_be_serialized['objects']]
        to_be_serialized['objects'] = [self.full_dehydrate(bundle) for bundle in bundles]
        to_be_serialized = self.alter_list_data_to_serialize(request, to_be_serialized)
        return self.create_response(request, to_be_serialized)

    def api_help(self, request, **kwargs):
        return render_to_response('repository/api/help.html', context_instance=RequestContext(request))

    def apply_filters(self, request, applicable_filters):
        base_object_list = super(LrResource, self).apply_filters(request, applicable_filters)

        # custom filters
        span = request.GET.get('span', None)
        on = request.GET.get('on', None)
        on_before = request.GET.get('on_before', None)
        on_after = request.GET.get('on_after', None)
        before = request.GET.get('before', None)
        after = request.GET.get('after', None)
        processed = request.GET.getlist('processed')
        validated = request.GET.getlist('validated')
        cleared = request.GET.getlist('cleared')

        filters = {}

        if span:
            filters.update(dict(metadataInfo__metadataCreationDate__range=[x.strip() for x in span.split(',')]))
        elif on:
            filters.update(dict(metadataInfo__metadataCreationDate__exact=on))
        elif on_before:
            filters.update(dict(metadataInfo__metadataCreationDate__lte=on_before))
        elif on_after:
            filters.update(dict(metadataInfo__metadataCreationDate__gte=on_after))
        elif before:
            filters.update(dict(metadataInfo__metadataCreationDate__lt=before))
        elif after:
            filters.update(dict(metadataInfo__metadataCreationDate__gt=after))

        if processed:
            filters.update(dict(management_object__is_processed_version=True))
        if validated:
            filters.update(dict(management_object__validated=True))
        if cleared:
            filters.update(dict(management_object__ipr_clearing__exact="cleared"))
        return base_object_list.filter(**filters).distinct()

    def apply_sorting(self, obj_list, options=None):
        if options:
            if 'latest' in options.get('sort', ''):
                return obj_list.order_by('-metadataInfo__metadataCreationDate')
            elif 'earliest' in options.get('sort', ''):
                return obj_list.order_by('metadataInfo__metadataCreationDate')
        return super(LrResource, self).apply_sorting(obj_list, options)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class VersionResource(ModelResource):
    class Meta:
        queryset = lr.versionInfoType_model.objects.all()
        resource_name = "version"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ProjectResource(ModelResource):
    class Meta:
        queryset = lr.projectInfoType_model.objects.all()
        resource_name = "project"
        include_resource_uri = False
        authorization = Authorization()
        excludes = EXCLUDES
        validation = validators.ELRCValidation(model=queryset.model)

    projectName = fields.DictField(attribute='projectName')
    projectShortName = fields.DictField(attribute='projectShortName', null=True)
    url = fields.ListField(attribute='url', null=True)
    fundingType = fields.ListField(attribute='fundingType')
    funder = fields.ListField(attribute='funder', null=True)
    fundingCountry = fields.ListField(attribute='fundingCountry', null=True)
    fundingCountryId = fields.ListField(attribute='fundingCountryId', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ResourceCreationResource(ModelResource):
    class Meta:
        queryset = lr.resourceCreationInfoType_model.objects.all()
        resource_name = "resourceCreation"
        include_resource_uri = False
        authorization = Authorization()

    resourceCreator = fields.ToManyField(ActorResource, 'resourceCreator', full=True, null=True)
    fundingProject = fields.ToManyField(ProjectResource, 'fundingProject', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []
                for related_bundle in bundle.data[field_name]:
                    if field_name == 'resourceCreator':
                        related_objs.append(resolve_actor(related_bundle))
                    elif field_name == 'fundingProject':
                        rel = related_bundle.obj.__class__.objects.filter(
                            projectName=related_bundle.obj.projectName,
                            projectShortName=related_bundle.obj.projectShortName).first()
                        if rel:
                            related_objs.append(rel)
                        else:
                            rel = ProjectResource()
                            rel.save(related_bundle)
                            related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        else:
            super(ResourceCreationResource, self).save_m2m(bundle)


class DocumentResource(ModelResource):
    class Meta:
        queryset = lr.documentInfoType_model.objects.all()
        resource_name = "document"
        include_resource_uri = False
        authorization = Authorization()
        excludes = EXCLUDES

    title = fields.DictField(attribute='title')
    author = fields.ListField(attribute='author', null=True)
    editor = fields.ListField(attribute='editor', null=True)
    publisher = fields.ListField(attribute='publisher', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class DocumentUnstructuredStringResource(ModelResource):
    class Meta:
        queryset = lr.documentUnstructuredString_model.objects.all()
        resource_name = "document_unstructured"
        include_resource_uri = False
        authorization = Authorization()

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class DocumentationResource(ModelResource):
    class Meta:
        queryset = lr.documentationInfoType_model.objects.all()
        resource_name = "documentation"
        include_resource_uri = False
        authorization = Authorization()

    def dehydrate(self, bundle):
        instance_class = bundle.obj.as_subclass()
        if isinstance(instance_class, documentInfoType_model):
            bundle.data['documentInfo'] = None
            document_res = DocumentResource()
            document_bundle = document_res.build_bundle(obj=instance_class, request=bundle.request)
            bundle.data['documentInfo'] = document_res.full_dehydrate(document_bundle).data
        elif isinstance(instance_class, documentUnstructuredString_model):
            bundle.data['documentUnstructured'] = None
            document_unstrucured_res = DocumentUnstructuredStringResource()
            document_unstrucured_bundle = document_unstrucured_res.build_bundle(
                obj=instance_class, request=bundle.request
            )
            bundle.data['documentUnstructured'] = document_unstrucured_res.full_dehydrate(
                document_unstrucured_bundle
            ).data
        return clean_bundle(bundle)

    def save(self, bundle, skip_errors=False):
        if bundle.data.get('documentInfo'):
            bundle.data = bundle.data.get('documentInfo')
            doc_res = DocumentResource()
            doc_bundle = doc_res.save(
                doc_res.build_bundle(data=bundle.data, request=bundle.request)
            )
            for f in doc_bundle.obj._meta.get_all_field_names():
                if bundle.data.get(f):
                    setattr(doc_bundle.obj, f, bundle.data[f])
            bundle.data = {}
            doc_bundle.obj.save()
            bundle.obj.id = doc_bundle.obj.id
            super(DocumentationResource, self).save(bundle)
        elif bundle.data.get('documentUnstructured'):
            bundle.data['value'] = bundle.data.get('documentUnstructured')
            doc_res = DocumentUnstructuredStringResource()
            doc_bundle = doc_res.save(doc_res.build_bundle(data=bundle.data, request=bundle.request))
            for f in doc_bundle.obj._meta.get_all_field_names():
                if bundle.data.get(f):
                    setattr(doc_bundle.obj, f, bundle.data[f])
            bundle.data = {}
            doc_bundle.obj.save()
            bundle.obj.id = doc_bundle.obj.id
            super(DocumentationResource, self).save(bundle)


class ResourceDocumentationResource(ModelResource):
    class Meta:
        queryset = lr.resourceDocumentationInfoType_model.objects.all()
        resource_name = "resourceDocumentation"
        include_resource_uri = False
        authorization = Authorization()

    # TODO: save m2m
    documentation = fields.ToManyField(DocumentationResource, 'documentation', full=True, null=True)
    samplesLocation = fields.ListField(attribute='samplesLocation', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ValidationResource(ModelResource):
    class Meta:
        queryset = lr.validationInfoType_model.objects.all()
        resource_name = "validation"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    validated = fields.BooleanField(attribute='validated')
    validationReport = fields.ToManyField(DocumentationResource, 'validationReport', full=True, null=True)
    validator = fields.ToManyField(ActorResource, 'validator', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []
                for related_bundle in bundle.data[field_name]:
                    if field_name == 'validator':
                        # check target subclass
                        if related_bundle.data.get('personInfo'):
                            surname = related_bundle.data.get('personInfo').get('surname')
                            given_name = related_bundle.data.get('personInfo').get('givenName')
                            email = related_bundle.data.get('personInfo').get('communicationInfo').get('email')

                            rel = lr.personInfoType_model.objects.get(
                                surname=surname,
                                communicationInfo__email=email)
                            if rel:
                                related_objs.append(rel)
                            else:
                                rel = PersonResource()
                                person_bundle = rel.save(
                                    rel.build_bundle(data=related_bundle.data.get('personInfo'))
                                )
                                # force some fields to be saved
                                person_bundle.obj.surname = surname
                                person_bundle.obj.givenName = given_name
                                person_bundle.obj.save()
                                # related_bundle.obj.id = person_bundle.obj.id
                                # rel.save(related_bundle)
                                related_objs.append(person_bundle.obj)
                        elif related_bundle.data.get('organizationInfo'):
                            organizationName = related_bundle.data.get('organizationInfo').get('organizationName')
                            organizationShortName = related_bundle.data.get('organizationInfo').get(
                                'organizationShortName')
                            email = related_bundle.data.get('organizationInfo').get('communicationInfo').get('email')

                            rel = lr.organizationInfoType_model.objects.get(
                                organizationName=organizationName)
                            if rel:
                                related_objs.append(rel)
                            else:
                                rel = OrganizationResource()
                                org_bundle = rel.save(
                                    rel.build_bundle(data=related_bundle.data.get('organizationInfo'))
                                )
                                # force some fields to be saved
                                org_bundle.obj.organizationName = organizationName
                                org_bundle.obj.organizationShortName = organizationShortName
                                org_bundle.obj.save()
                                related_objs.append(org_bundle.obj)
                    else:
                        # It is a licence. Create a new one
                        rel = LicenceResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        super(ValidationResource, self).save_m2m(bundle)


class TargetResourceNameResource(ModelResource):
    class Meta:
        queryset = lr.targetResourceInfoType_model.objects.all()
        resource_name = "target_resource_name"
        include_resource_uri = False
        authorization = Authorization()

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class RelationResource(ModelResource):
    class Meta:
        queryset = lr.relationInfoType_model.objects.all()
        resource_name = "relation"
        include_resource_uri = False
        authorization = Authorization()

    relatedResource = fields.ToOneField(TargetResourceNameResource, 'relatedResource', full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LingualityResource(ModelResource):
    class Meta:
        queryset = lr.lingualityInfoType_model.objects.all()
        resource_name = "linguality"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LanguageResource(ModelResource):
    class Meta:
        queryset = lr.languageInfoType_model.objects.all()
        resource_name = "language"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    variant = fields.ListField(attribute='variant', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class SizeResource(ModelResource):
    class Meta:
        queryset = lr.sizeInfoType_model.objects.all()
        resource_name = "size"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    size = fields.IntegerField(attribute='size')

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class TextFormatResource(ModelResource):
    class Meta:
        queryset = lr.textFormatInfoType_model.objects.all()
        resource_name = "text_format"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    sizePerTextFormat = fields.ToOneField(SizeResource, 'sizePerTextFormat', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class CharacterEncodingResource(ModelResource):
    class Meta:
        queryset = lr.characterEncodingInfoType_model.objects.all()
        resource_name = "character_encoding"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    sizePerCharacterEncoding = fields.ToOneField(SizeResource, 'sizePerTextFormat', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class AnnotationResource(ModelResource):
    class Meta:
        queryset = lr.annotationInfoType_model.objects.all()
        resource_name = "annotation_set"
        include_resource_uri = True
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    annotationType = fields.CharField(attribute='annotationType')
    segmentationLevel = fields.ListField(attribute='segmentationLevel', null=True)
    conformanceToStandardsBestPractices = fields.ListField(attribute='conformanceToStandardsBestPractices', null=True)
    annotationManual = fields.ToManyField(DocumentationResource, 'annotationManual', full=True, null=True)
    annotationTool = fields.ToManyField(TargetResourceNameResource, 'annotationTool', full=True, null=True)
    sizePerAnnotation = fields.ToOneField(SizeResource, 'sizePerAnnotation', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class DomainResource(ModelResource):
    class Meta:
        queryset = lr.domainInfoType_model.objects.all()
        resource_name = "domain"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    sizePerDomain = fields.ToOneField(SizeResource, 'sizePerDomain', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class TextClassificationResource(ModelResource):
    class Meta:
        queryset = lr.textClassificationInfoType_model.objects.all()
        resource_name = "text_classification"
        include_resource_uri = False
        authorization = Authorization()

    sizePerTextClassification = fields.ToOneField(SizeResource, 'sizePerTextClassification', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class CreationResource(ModelResource):
    class Meta:
        queryset = lr.creationInfoType_model.objects.all()
        resource_name = "creation"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    creationModeDetails = fields.CharField(attribute='creationModeDetails')
    originalSource = fields.ToManyField(TargetResourceNameResource, 'originalSource', full=True, null=True)
    creationTool = fields.ToManyField(TargetResourceNameResource, 'creationTool', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save(self, bundle, skip_errors=False):
        bundle.data['creationModeDetails'] = bundle.data['creationModeDetails'].replace('\n', '')
        super(CreationResource, self).save(bundle)


class CorpusTextResource(ModelResource):
    class Meta:
        queryset = lr.corpusTextInfoType_model.objects.all()
        resource_name = "corpus_text_info"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    lingualityInfo = fields.ToOneField(LingualityResource, 'lingualityInfo', full=True)
    languageInfo = fields.ToManyField(LanguageResource, 'languageinfotype_model_set', full=True)
    sizeInfo = fields.ToManyField(SizeResource, 'sizeinfotype_model_set', full=True)
    textFormatInfo = fields.ToManyField(TextFormatResource, 'textformatinfotype_model_set', full=True)
    characterEncodingInfo = fields.ToManyField(CharacterEncodingResource,
                                               'characterencodinginfotype_model_set', full=True, null=True)
    annotationInfo = fields.ToManyField(AnnotationResource,
                                        'annotationinfotype_model_set', full=True, null=True)
    domainInfo = fields.ToManyField(DomainResource, 'domaininfotype_model_set', full=True, null=True)
    textClassificationInfo = fields.ToManyField(TextClassificationResource,
                                                'textclassificationinfotype_model_set', full=True, null=True)
    creationInfo = fields.ToOneField(CreationResource, 'creationInfo', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class CorpusMediaTypeResource(ModelResource):
    class Meta:
        queryset = lr.corpusMediaTypeType_model.objects.all()
        resource_name = "corpus_media_type"
        include_resource_uri = False
        allowed_methods = ['get', 'post', 'put', 'patch']
        authorization = Authorization()

    corpusTextInfo = fields.ToManyField(CorpusTextResource, 'corpustextinfotype_model_set',
                                        full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ResourceComponentTypeResource(ModelResource):
    class Meta:
        queryset = lr.resourceComponentTypeType_model.objects.all()
        resource_name = "resource_component"
        include_resource_uri = False
        authorization = Authorization()

    def dehydrate(self, bundle):
        instance_class = bundle.obj.as_subclass()
        if isinstance(instance_class, corpusInfoType_model):
            bundle.data['corpusInfo'] = None
            corpus_res = CorpusResource()
            corpus_bundle = corpus_res.build_bundle(obj=instance_class, request=bundle.request)
            bundle.data['corpusInfo'] = corpus_res.full_dehydrate(corpus_bundle).data
        elif isinstance(instance_class, lexicalConceptualResourceInfoType_model):
            bundle.data['lexicalConceptualResourceInfo'] = None
            lcr_res = LCRResource()
            lcr_bundle = lcr_res.build_bundle(obj=instance_class, request=bundle.request)
            bundle.data['lexicalConceptualResourceInfo'] = lcr_res.full_dehydrate(lcr_bundle).data
        elif isinstance(instance_class, languageDescriptionInfoType_model):
            bundle.data['languageDescriptionInfo'] = None
            language_description_res = LanguageDescriptionResource()
            language_description_bundle = language_description_res.build_bundle(
                obj=instance_class, request=bundle.request
            )
            bundle.data['languageDescriptionInfo'] = language_description_res.full_dehydrate(
                language_description_bundle
            ).data
        elif isinstance(instance_class, toolServiceInfoType_model):
            bundle.data['toolServiceInfo'] = None
            tool_res = ToolServiceResource()
            tool_bundle = tool_res.build_bundle(obj=instance_class, request=bundle.request)
            bundle.data['toolServiceInfo'] = tool_res.full_dehydrate(tool_bundle).data
        return clean_bundle(bundle)

    def save(self, bundle, skip_errors=False):
        if bundle.request.method == 'POST':
            if bundle.data.get('corpusInfo'):
                bundle.data = bundle.data.get('corpusInfo')
                corpus_res = CorpusResource()
                corpus_bundle = corpus_res.save(
                    corpus_res.build_bundle(data=bundle.data, request=bundle.request)
                )
                bundle.data = {}
                corpus_bundle.obj.save()
                bundle.obj.id = corpus_bundle.obj.id
                super(ResourceComponentTypeResource, self).save(bundle)
            elif bundle.data.get('lexicalConceptualResourceInfo'):
                bundle.data = bundle.data.get('lexicalConceptualResourceInfo')
                lcr_res = LCRResource()
                lcr_bundle = lcr_res.save(
                    lcr_res.build_bundle(data=bundle.data, request=bundle.request)
                )
                bundle.data = {}
                lcr_bundle.obj.save()
                bundle.obj.id = lcr_bundle.obj.id
                super(ResourceComponentTypeResource, self).save(bundle)
            elif bundle.data.get('languageDescriptionInfo'):
                bundle.data = bundle.data.get('languageDescriptionInfo')
                lg_res = LanguageDescriptionResource()
                lg_bundle = lg_res.save(
                    lg_res.build_bundle(data=bundle.data, request=bundle.request)
                )
                bundle.data = {}
                lg_bundle.obj.save()
                bundle.obj.id = lg_bundle.obj.id
                super(ResourceComponentTypeResource, self).save(bundle)
            elif bundle.data.get('toolServiceInfo'):
                bundle.data = bundle.data.get('toolServiceInfo')
                tool_res = ToolServiceResource()
                tool_bundle = tool_res.save(
                    tool_res.build_bundle(data=bundle.data, request=bundle.request)
                )
                bundle.data = {}
                tool_bundle.obj.save()
                bundle.obj.id = tool_bundle.obj.id
                super(ResourceComponentTypeResource, self).save(bundle)
        else:
            super(ResourceComponentTypeResource, self).save(bundle)


class CorpusResource(ModelResource):
    class Meta:
        queryset = lr.corpusInfoType_model.objects.all()
        resource_name = "corpus"
        include_resource_uri = False
        authorization = Authorization()
        allowed_methods = ['get', 'post', 'put', 'patch']

    corpusMediaType = fields.ToOneField(CorpusMediaTypeResource, 'corpusMediaType',
                                        full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LCREncodingResource(ModelResource):
    class Meta:
        queryset = lr.lexicalConceptualResourceEncodingInfoType_model.objects.all()
        resource_name = "lexical_conceptual_encoding"
        include_resource_uri = False
        authorization = Authorization()

    encodingLevel = fields.ListField(attribute='encodingLevel')
    linguisticInformation = fields.ListField(attribute='linguisticInformation', null=True)
    conformanceToStandardsBestPractices = fields.ListField(attribute='conformanceToStandardsBestPractices', null=True)
    theoreticModel = fields.ListField(attribute='theoreticModel', null=True)
    externalRef = fields.ListField(attribute='externalRef', null=True)
    extratextualInformation = fields.ListField(attribute='extratextualInformation', null=True)
    extraTextualInformationUnit = fields.ListField(attribute='extraTextualInformationUnit', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LCRTextResource(ModelResource):
    class Meta:
        queryset = lr.lexicalConceptualResourceTextInfoType_model.objects.all()
        resource_name = "lexical_conceptual_text"
        include_resource_uri = False
        authorization = Authorization()

    lingualityInfo = fields.ToOneField(LingualityResource, 'lingualityInfo', full=True)
    languageInfo = fields.ToManyField(LanguageResource, 'languageinfotype_model_set', full=True)
    sizeInfo = fields.ToManyField(SizeResource, 'sizeinfotype_model_set', full=True)
    textFormatInfo = fields.ToManyField(TextFormatResource, 'textformatinfotype_model_set', full=True)
    characterEncodingInfo = fields.ToManyField(CharacterEncodingResource,
                                               'characterencodinginfotype_model_set', full=True, null=True)
    domainInfo = fields.ToManyField(DomainResource,
                                    'domaininfotype_model_set', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LCRMediaTypeResource(ModelResource):
    class Meta:
        queryset = lr.lexicalConceptualResourceMediaTypeType_model.objects.all()
        resource_name = "lexical_conceptual_media"
        include_resource_uri = False
        authorization = Authorization()

    lexicalConceptualResourceTextInfo = fields.ToOneField(LCRTextResource,
                                                          'lexicalConceptualResourceTextInfo', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LCRResource(ModelResource):
    class Meta:
        queryset = lr.lexicalConceptualResourceInfoType_model.objects.all()
        resource_name = "lexical_conceptual_resource"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    lexicalConceptualResourceType = fields.CharField(attribute='lexicalConceptualResourceType', null=False)

    lexicalConceptualResourceEncodingInfo = fields.ToOneField(LCREncodingResource,
                                                              'lexicalConceptualResourceEncodingInfo',
                                                              full=True, null=True)
    lexicalConceptualResourceMediaType = fields.ToOneField(LCRMediaTypeResource,
                                                           'lexicalConceptualResourceMediaType', full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save(self, bundle, skip_errors=False):
        bundle.obj.lexicalConceptualResourceType = bundle.data['lexicalConceptualResourceType']
        return super(LCRResource, self).save(bundle)


class LanguageDescriptionEncodingResource(ModelResource):
    class Meta:
        queryset = lr.languageDescriptionEncodingInfoType_model.objects.all()
        resource_name = "language_description_encoding"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    encodingLevel = fields.ListField(attribute='encodingLevel')
    conformanceToStandardsBestPractices = fields.ListField(attribute='conformanceToStandardsBestPractices', null=True)
    theoreticModel = fields.ListField(attribute='theoreticModel', null=True)
    task = fields.ListField(attribute='task', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LanguageDescriptionTextResource(ModelResource):
    class Meta:
        queryset = lr.languageDescriptionTextInfoType_model.objects.all()
        resource_name = "language_description_text"
        include_resource_uri = False
        authorization = Authorization()

    lingualityInfo = fields.ToOneField(LingualityResource, 'lingualityInfo', full=True)
    languageInfo = fields.ToManyField(LanguageResource, 'languageinfotype_model_set', full=True)
    sizeInfo = fields.ToManyField(SizeResource, 'sizeinfotype_model_set', full=True, null=True)
    textFormatInfo = fields.ToManyField(TextFormatResource, 'textformatinfotype_model_set', full=True, null=True)
    characterEncodingInfo = fields.ToManyField(CharacterEncodingResource,
                                               'characterencodinginfotype_model_set', full=True, null=True)
    domainInfo = fields.ToManyField(DomainResource, 'domaininfotype_model_set', full=True, null=True)
    textClassificationInfo = fields.ToManyField(TextClassificationResource,
                                                'textclassificationinfotype_model_set', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LanguageDescriptionMediaTypeResource(ModelResource):
    class Meta:
        queryset = lr.languageDescriptionMediaTypeType_model.objects.all()
        resource_name = "ld_media_type"
        include_resource_uri = False
        authorization = Authorization()

    languageDescriptionTextInfo = fields.ToOneField(LanguageDescriptionTextResource,
                                                    'languageDescriptionTextInfo', full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class LanguageDescriptionResource(ModelResource):
    class Meta:
        queryset = lr.languageDescriptionInfoType_model.objects.all()
        resource_name = "language_description"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    languageDescriptionType = fields.CharField(attribute='languageDescriptionType')
    languageDescriptionEncodingInfo = fields.ToOneField(LanguageDescriptionEncodingResource,
                                                        'languageDescriptionEncodingInfo', full=True, null=True)
    languageDescriptionMediaType = fields.ToOneField(LanguageDescriptionMediaTypeResource,
                                                     'languageDescriptionMediaType', full=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save(self, bundle, skip_errors=False):
        bundle.obj.languageDescriptionType = bundle.data['languageDescriptionType']
        return super(LanguageDescriptionResource, self).save(bundle)


class LanguageSetResource(ModelResource):
    class Meta:
        queryset = lr.languageSetInfoType_model.objects.all()
        resource_name = "language_set"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    variant = fields.ListField(attribute='variant', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class DomainSetResource(ModelResource):
    class Meta:
        queryset = lr.domainSetInfoType_model.objects.all()
        resource_name = "domain_set"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    domain = fields.ListField(attribute='domain')
    domainId = fields.ListField(attribute='domainId')
    subdomain = fields.ListField(attribute='subdomain', null=True)
    subdomainId = fields.ListField(attribute='subdomainId', null=True)
    conformanceToClassificationScheme = fields.ListField(attribute='conformanceToClassificationScheme', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class InputResource(ModelResource):
    class Meta:
        queryset = lr.inputInfoType_model.objects.all()
        resource_name = "tool_input"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    resourceType = fields.ListField(attribute='resourceType', null=True)
    dataFormat = fields.ListField(attribute='dataFormat', null=True)
    languageSetInfo = fields.ToManyField(LanguageSetResource, 'languagesetinfotype_model_set', full=True, null=True)
    languageVarietyName = fields.ListField(attribute='languageVarietyName', null=True)
    characterEncoding = fields.ListField(attribute='characterEncoding', null=True)
    domainSetInfo = fields.ToManyField(DomainSetResource, 'domainSetInfo')
    annotationType = fields.ListField(attribute='annotationType', null=True)
    conformanceToStandardsBestPractices = fields.ListField(attribute='conformanceToStandardsBestPractices', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class OutputResource(ModelResource):
    class Meta:
        queryset = lr.outputInfoType_model.objects.all()
        resource_name = "tool_output"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    mediaType = fields.ListField(attribute='mediaType')
    resourceType = fields.ListField(attribute='resourceType', null=True)
    dataFormat = fields.ListField(attribute='dataFormat', null=True)
    languageSetInfo = fields.ToManyField(LanguageSetResource, 'languagesetinfotype_model_set', full=True, null=True)
    languageVarietyName = fields.ListField(attribute='languageVarietyName', null=True)
    characterEncoding = fields.ListField(attribute='characterEncoding', null=True)
    annotationType = fields.ListField(attribute='annotationType', null=True)
    conformanceToStandardsBestPractices = fields.ListField(attribute='conformanceToStandardsBestPractices', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class DependenciesResource(ModelResource):
    class Meta:
        queryset = lr.dependenciesInfoType_model.objects.all()
        resource_name = "dependencies"
        include_resource_uri = False
        authorization = Authorization()

    requiredSoftware = fields.ToManyField(TargetResourceNameResource, 'requiredSoftware', full=True, null=True)
    requiredLRs = fields.ToManyField(TargetResourceNameResource, 'requiredLRs', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ToolServiceOperationResource(ModelResource):
    class Meta:
        queryset = lr.toolServiceOperationInfoType_model.objects.all()
        resource_name = "tool_operation"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    operatingSystem = fields.ListField(attribute='operatingSystem', null=True)
    dependenciesInfo = fields.ToOneField(DependenciesResource, 'dependenciesInfo', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ToolServiceEvaluationResource(ModelResource):
    class Meta:
        queryset = lr.toolServiceEvaluationInfoType_model.objects.all()
        resource_name = "tool_evaluation"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    evaluationLevel = fields.ListField(attribute='evaluationLevel', null=True)
    evaluationCriteria = fields.ListField(attribute='evaluationCriteria', null=True)
    evaluationMeasure = fields.ListField(attribute='evaluationMeasure', null=True)
    evaluationReport = fields.ToManyField(DocumentationResource, 'evaluationReport', null=True)
    evaluationTool = fields.ToManyField(TargetResourceNameResource, 'evaluationTool', null=True)
    evaluator = fields.ToManyField(ActorResource, 'evaluator', null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []
                for related_bundle in bundle.data[field_name]:
                    if field_name == 'evaluator':
                        related_objs.append(resolve_actor(related_bundle))
                    else:
                        # It is a licence. Create a new one
                        rel = LicenceResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        else:
            super(ToolServiceEvaluationResource, self).save_m2m(bundle)


class ToolServiceCreationResource(ModelResource):
    class Meta:
        queryset = lr.toolServiceCreationInfoType_model.objects.all()
        resource_name = "tool_creation"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    implementationLanguage = fields.ListField(attribute='implementationLanguage', null=True)
    formalism = fields.ListField(attribute='formalism', null=True)
    originalSource = fields.ToManyField(TargetResourceNameResource, 'originalSource', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class ToolServiceResource(ModelResource):
    class Meta:
        queryset = lr.toolServiceInfoType_model.objects.all()
        resource_name = "tool_service"
        include_resource_uri = False
        authorization = Authorization()
        validation = validators.ELRCValidation(model=queryset.model)

    function = fields.ListField(attribute='function')
    inputInfo = fields.ToOneField(InputResource, 'inputInfo', full=True, null=True)
    outputInfo = fields.ToOneField(OutputResource, 'outputInfo', full=True, null=True)
    toolServiceOperationInfo = fields.ToOneField(ToolServiceOperationResource,
                                                 'toolServiceOperationInfo', full=True, null=True)
    toolServiceEvaluationInfo = fields.ToOneField(ToolServiceEvaluationResource,
                                                  'toolServiceEvaluationInfo', full=True, null=True)
    toolServiceCreationInfo = fields.ToOneField(ToolServiceCreationResource,
                                                'toolServiceCreationInfo', full=True, null=True)

    def dehydrate(self, bundle):
        return clean_bundle(bundle)


class FullLrResource(ModelResource):
    class Meta:
        queryset = lr.resourceInfoType_model.objects.filter(storage_object__deleted=False)
        # allowed_methods = ['get', 'post', 'patch', 'put']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'post', 'patch', 'put']
        resource_name = 'lr'
        collection_name = 'resources'
        authentication = Authentication()
        authorization = EditorUserAuthorization()
        always_return_data = True
        include_resource_uri = False
        field_order = ('identificationInfo', 'distributionInfo', 'contactPerson')

    identificationInfo = fields.ToOneField(IdentificationResource, 'identificationInfo', full=True)
    distributionInfo = fields.ToManyField(DistributionResource,
                                          'distributioninfotype_model_set', full=True)
    contactPerson = fields.ToManyField(PersonResource, 'contactPerson', full=True)
    metadataInfo = fields.ToOneField(MetadataInfoResource, 'metadataInfo', full=True)
    versionInfo = fields.ToOneField(VersionResource, 'versionInfo', full=True, null=True)
    resourceCreationInfo = fields.ToOneField(ResourceCreationResource,
                                             'resourceCreationInfo', full=True, null=True)
    resourceDocumentationInfo = fields.ToOneField(ResourceDocumentationResource,
                                                  'resourceDocumentationInfo', full=True, null=True)
    validationInfo = fields.ToManyField(ValidationResource,
                                        'validationinfotype_model_set', full=True, null=True)
    relationInfo = fields.ToManyField(RelationResource, 'relationinfotype_model_set', full=True, null=True)

    resourceComponentType = fields.ToOneField(ResourceComponentTypeResource, 'resourceComponentType', full=True)

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/my%s$" % (self._meta.resource_name, trailing_slash()),
                self.wrap_view('get_my'), name="api_get_my"),
        ]

    def get_my(self, request, **kwargs):
        qs = self._meta.queryset.filter(Q(owners=request.user))
        bundles = [self.build_bundle(obj=result, request=request) for result in qs]
        to_be_serialized = [self.full_dehydrate(bundle) for bundle in bundles]
        return self.create_response(request, to_be_serialized)

    def get_object_list(self, request):
        if is_member(request.user, 'ecmembers'):
            return self._meta.queryset.exclude(
                Q(storage_object__publication_status='i') & ~Q(owners=request.user)
            )
        else:
            return self._meta.queryset

    def log_change(self, bundle, object, message):
        """
        Log that an object has been successfully changed.

        The default implementation creates an admin LogEntry object.
        """
        from django.contrib.admin.models import LogEntry, CHANGE
        LogEntry.objects.log_action(
            user_id=bundle.request.user.pk,
            content_type_id=get_content_type_for_model(object).pk,
            object_id=object.pk,
            object_repr=force_text(object),
            action_flag=CHANGE,
            change_message=message
        )

    def save(self, bundle, skip_errors=False):
        # first save to get id
        super(FullLrResource, self).save(bundle)
        # add ownwer and save again to set management_object partner
        if not bundle.obj.owners.all():
            bundle.obj.owners.add(bundle.request.user)
            bundle.obj.save()

        # create storage folder
        bundle.obj.storage_object.update_storage()
        return super(FullLrResource, self).save(bundle)

    def dehydrate(self, bundle):
        if bundle.request.method == 'POST':
            # bundle.data.clear()
            bundle.data.update({"ID": bundle.obj.id})
            return bundle
        elif bundle.request.method in ['PUT', 'PATCH']:
            # bundle.data.clear()
            # bundle.data.update({"messages": ["Resource Saved"]})
            return bundle
        resource = dict()
        resource['resourceInfo'] = bundle.data
        bundle.data = resource
        bundle.data['download_location'] = "{}/repository/download/{}".format(
            DJANGO_URL, bundle.obj.storage_object.identifier)
        bundle.data['publication_status'] = pub_status.get(bundle.obj.storage_object.publication_status)
        return clean_bundle(bundle, root='resourceInfo')

    def hydrate(self, bundle):
        try:
            bundle.data = bundle.data['resourceInfo']
        except KeyError:
            pass
        return bundle

    def update_in_place(self, request, original_bundle, new_data):
        """
        Update the object in original_bundle in-place using new_data.
        """
        messages = []
        if original_bundle.obj.management_object.ipr_clearing == 'cleared':
            # if ipr is cleared, do not update distributionInfo, user the existing values
            dr = DistributionResource()
            new_data['resourceInfo']['distributionInfo'] = [json.loads(dr.serialize(request, d, 'application/json'))
                                                            for d in original_bundle.data['distributionInfo']]
            messages.append('Resource {} has been marked as "IPR cleared". Distribution info updates have been ignored'.
                            format(original_bundle.obj.id))
        original_bundle.data.update(**dict_strip_unicode_keys(new_data))

        # Now we've got a bundle with the new data sitting in it and we're
        # we're basically in the same spot as a PUT request. SO the rest of this
        # function is cribbed from put_detail.
        self.alter_deserialized_detail_data(request, original_bundle.data)
        kwargs = {
            self._meta.detail_uri_name: self.get_bundle_detail_data(original_bundle),
            'request': request,
            'messages': messages
        }
        return self.obj_update(bundle=original_bundle, **kwargs)

    def obj_update(self, bundle, skip_errors=False, **kwargs):
        """
        A ORM-specific implementation of ``obj_update``.
        """
        bundle_detail_data = self.get_bundle_detail_data(bundle)
        arg_detail_data = kwargs.get(self._meta.detail_uri_name)
        if bundle_detail_data is None or (arg_detail_data is not None and str(bundle_detail_data) != str(arg_detail_data)):
            try:
                lookup_kwargs = self.lookup_kwargs_with_identifiers(bundle, kwargs)
            except:
                # if there is trouble hydrating the data, fall back to just
                # using kwargs by itself (usually it only contains a "pk" key
                # and this will work fine.
                lookup_kwargs = kwargs

            try:
                bundle.obj = self.obj_get(bundle=bundle, **lookup_kwargs)
            except ObjectDoesNotExist:
                raise NotFound("A model instance matching the provided arguments could not be found.")

        bundle = self.full_hydrate(bundle)
        bundle.data.update({'messages':kwargs.pop('messages')})
        print bundle.data['messages']
        return self.save(bundle, skip_errors=skip_errors)

    def save_m2m(self, bundle):
        if bundle.request.method in ['POST', 'PATCH']:
            for field_name, field_object in self.fields.items():
                if not getattr(field_object, 'is_m2m', False):
                    continue
                if not field_object.attribute:
                    continue
                if field_object.readonly:
                    continue
                # Get the manager.
                related_mngr = getattr(bundle.obj, field_object.attribute)
                related_objs = []

                for related_bundle in bundle.data[field_name]:
                    if field_name == 'contactPerson':

                        rel = related_bundle.obj.__class__.objects.filter(
                            surname=related_bundle.obj.surname,
                            communicationInfo__email=related_bundle.obj.communicationInfo.email).first()
                        if rel:
                            related_objs.append(rel)
                        else:
                            rel = PersonResource()
                            rel.save(related_bundle)
                            related_objs.append(related_bundle.obj)
                    elif field_name == 'distributionInfo':
                        # This is OneToMany, not reusable
                        rel = DistributionResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                    elif field_name == 'validationInfo':
                        # This is OneToMany, not reusable
                        rel = ValidationResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                    elif field_name == 'relationInfo':
                        # This is OneToMany, not reusable
                        rel = RelationResource()
                        rel.save(related_bundle)
                        related_objs.append(related_bundle.obj)
                related_mngr.add(*related_objs)
        else:
            super(FullLrResource, self).save_m2m(bundle)
