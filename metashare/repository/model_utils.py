"""
Methods for model data conversion between different representations.
"""

import logging

import os
from django.db.models import OneToOneField, Sum

from metashare.repository.dataformat_choices import MIMETYPEVALUE_TO_MIMETYPELABEL
from metashare.repository.models import resourceInfoType_model, \
    corpusInfoType_model, lexicalConceptualResourceInfoType_model, \
    languageDescriptionInfoType_model, toolServiceInfoType_model
from metashare.repository.templatetags.replace import pretty_camel
from metashare.settings import LOG_HANDLER, PROCESSING_MAXIMUM_UPLOAD_SIZE
from metashare.stats.models import LRStats

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)


def get_related_models(instance, parent):
    """
    Returns a list containing model names of classes that reference instance.
    
    Related models for a given class X are all classes Y that have a relation
    set to X via a ForeignKey field.
    """
    LOGGER.info('get_related_models({0}) called.'.format(
        instance.__class__.__name__))

    # If a parent is given, compute the corresponding parent_set String.
    parent_set = None
    if parent:
        parent_set = '{0}_set'.format(parent).lower()

    # Related model class names should have this suffix.
    related_suffix = '_{0}'.format(instance.__class__.__name__)

    result = []
    for name in dir(instance):
        if name.endswith('_set'):
            if name != parent_set:
                model_instance = getattr(instance, name)
                model_name = model_instance.model.__name__

                LOGGER.info('{0} ({1})'.format(name, model_name))

                if model_name.endswith(related_suffix):
                    result.append(model_name)

    return result


def get_root_resources(*instances):
    """
    Returns the set of `resourceInfoType_model` instances which somewhere
    contain the given model instances.
    
    If any of the given instances is a `resourceInfoType_model` itself, then
    this instance will be in the returned set, too. The returned set can be
    empty.
    """
    return _get_root_resources(set(), *instances)


def _get_root_resources(ignore, *instances):
    """
    Returns the set of `resourceInfoType_model` instances which somewhere
    contain the given model instances.
    
    If any of the given instances is a `resourceInfoType_model` itself, then
    this instance will be in the returned set, too. The returned set can be
    empty. All instances which are found in the given ignore set will not be
    looked at. The ignore set will be extended with the given instances.
    """
    result = set()
    for instance in instances:
        if instance in ignore:
            continue
        ignore.add(instance)

        # `resourceInfoType_model` instances are our actual results
        if instance.__class__.__name__ == u'resourceInfoType_model':
            result.add(instance)
        # an instance may be None, in which case we ignore it
        elif hasattr(instance, '_meta'):
            # There are 3 possibilities for going backward in our model graph:

            # case (1): we have to follow a `ForeignKey` with a name starting
            #   with "back_to_":
            for rel in [r for r in instance._meta.get_all_field_names()
                        if r.startswith('back_to_')]:
                result.update(_get_root_resources(ignore,
                                                  getattr(instance, rel)))

            # case (2): we have to follow "reverse" `ForeignKey`s and
            #   `OneToOneField`s which are pointing at the current instance from
            #   a model which is closer to the searched root model:
            for rel in instance._meta.get_all_related_objects():
                accessor_name = rel.get_accessor_name()
                # the accessor name may point to a field which is None, so test
                # first, if a field instance is actually available (?)
                if hasattr(instance, accessor_name):
                    accessor = getattr(instance, accessor_name)
                    if isinstance(rel.field, OneToOneField):
                        # in the case of `OneToOneField`s the accessor is the
                        # new instance itself
                        result.update(_get_root_resources(ignore, accessor))
                    else:
                        result.update(_get_root_resources(ignore,
                                                          *accessor.all()))

            # case (2): we have to follow the "reverse" part of a `ManyToMany`
            #   field which is pointing at the current instance from a model
            #   which is closer to the searched root model:
            for rel in instance._meta.get_all_related_many_to_many_objects():
                result.update(_get_root_resources(ignore,
                                                  *getattr(instance, rel.get_accessor_name()).all()))

    return result


def get_resource_linguality_infos(res_obj):
    """
    Returns a list of all linguality types of the given language resource
    instance.
    """
    result = []
    corpus_media = res_obj.resourceComponentType.as_subclass()

    if isinstance(corpus_media, corpusInfoType_model):
        media_type = corpus_media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            result.append(corpus_info.lingualityInfo
                          .get_lingualityType_display())

    elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            result.append(lcr_media_type.lexicalConceptualResourceTextInfo \
                          .lingualityInfo.get_lingualityType_display())

    elif isinstance(corpus_media, languageDescriptionInfoType_model):
        ld_media_type = corpus_media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.append(ld_media_type.languageDescriptionTextInfo \
                          .lingualityInfo.get_lingualityType_display())

    return result


def get_resource_license_types(res_obj):
    """
    Returns a list of license under which the given language resource is
    available.
    """
    return [pretty_camel(licence_info.licence) for distributionInfo in
            res_obj.distributioninfotype_model_set.all()
            for licence_info in
            distributionInfo.licenceInfo.all()]


def get_resource_attribution_texts(res_obj):
    """
    Returns a list of attribution texts for the given resource. The attribution
    texts that are collected, are only in the default language
    """
    return [distributionInfo.get_default_attributionText() for distributionInfo in
            res_obj.distributioninfotype_model_set.all()]


def get_resource_media_types(res_obj):
    """
    Returns a list of all media types of the given language resource instance.
    """
    result = []
    corpus_media = res_obj.resourceComponentType.as_subclass()

    if isinstance(corpus_media, corpusInfoType_model):
        media_type = corpus_media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            result.append(corpus_info.mediaType)

    elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            result.append(
                lcr_media_type.lexicalConceptualResourceTextInfo.mediaType)

    elif isinstance(corpus_media, languageDescriptionInfoType_model):
        ld_media_type = corpus_media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.append(ld_media_type.languageDescriptionTextInfo.mediaType)

    elif isinstance(corpus_media, toolServiceInfoType_model):
        if corpus_media.inputInfo:
            result.append(corpus_media.inputInfo \
                          .get_mediaType_display())
        if corpus_media.outputInfo:
            result.append(corpus_media.outputInfo \
                          .get_mediaType_display())

    result_lower = []
    for res in result:
        result_lower.append(res.lower())

    return result_lower


def get_resource_dataformats(res_obj):
    dataFormat_list = []
    corpus_media = res_obj.resourceComponentType.as_subclass()

    if isinstance(corpus_media, corpusInfoType_model):
        media_type = corpus_media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            dataFormat_list.extend([MIMETYPEVALUE_TO_MIMETYPELABEL[dataFormat.dataFormat]
                                    if dataFormat.dataFormat in MIMETYPEVALUE_TO_MIMETYPELABEL
                                    else dataFormat.dataFormat for dataFormat in
                                    corpus_info.textformatinfotype_model_set.all()])

    elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            dataFormat_list.extend([MIMETYPEVALUE_TO_MIMETYPELABEL[dataFormat.dataFormat]
                                    if dataFormat.dataFormat in MIMETYPEVALUE_TO_MIMETYPELABEL
                                    else dataFormat.dataFormat for dataFormat in
                                    lcr_media_type.lexicalConceptualResourceTextInfo \
                                   .textformatinfotype_model_set.all()])

    elif isinstance(corpus_media, languageDescriptionInfoType_model):
        ld_media_type = corpus_media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            dataFormat_list.extend([MIMETYPEVALUE_TO_MIMETYPELABEL[dataFormat.dataFormat]
                                    if dataFormat.dataFormat in MIMETYPEVALUE_TO_MIMETYPELABEL
                                    else dataFormat.dataFormat for dataFormat in
                                    ld_media_type.languageDescriptionTextInfo \
                                   .textformatinfotype_model_set.all()])

    elif isinstance(corpus_media, toolServiceInfoType_model):
        if corpus_media.inputInfo:
            dataFormat_list.extend(corpus_media.inputInfo.dataFormat)
        if corpus_media.outputInfo:
            dataFormat_list.extend(corpus_media.outputInfo.dataFormat)

    return dataFormat_list


def get_resource_encodings(res_obj):
    encoding_list = []
    corpus_media = res_obj.resourceComponentType.as_subclass()

    if isinstance(corpus_media, corpusInfoType_model):
        media_type = corpus_media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            encoding_list.extend([chr.characterEncoding for chr in
                                  corpus_info.characterencodinginfotype_model_set.all()])

    elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            encoding_list.extend([chr.characterEncoding for chr in
                                  lcr_media_type.lexicalConceptualResourceTextInfo \
                                 .characterencodinginfotype_model_set.all()])

    elif isinstance(corpus_media, languageDescriptionInfoType_model):
        ld_media_type = corpus_media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            encoding_list.extend([chr.characterEncoding for chr in
                                  ld_media_type.languageDescriptionTextInfo \
                                 .characterencodinginfotype_model_set.all()])

    elif isinstance(corpus_media, toolServiceInfoType_model):
        if corpus_media.inputInfo:
            encoding_list.extend(corpus_media.inputInfo.characterEncoding)
        if corpus_media.outputInfo:
            encoding_list.extend(corpus_media.outputInfo.characterEncoding)

    return encoding_list


def is_processable(res_obj):
    """
    Determine if a resource is processable (and at which extent) by ELRC services
    by checking a. if it contains valid formats, b. is less than or equal to 30mb
    This function is mainly to be used to build the solr facet.
    Returns: tuple
    """
    valid_formats = {'HTML', 'XHTML', 'Plain text', 'PDF', 'MS-Word doc', 'MS-Word docx'}
    data_formats = set(get_resource_dataformats(res_obj))
    download_path = res_obj.storage_object.get_download()
    existing_and_size_permitted = False
    if download_path and os.stat(download_path).st_size <= PROCESSING_MAXIMUM_UPLOAD_SIZE:
        existing_and_size_permitted = True
    return ("YES" if (bool(valid_formats & data_formats) and existing_and_size_permitted) else "NO",
            True if valid_formats & data_formats == data_formats else False)


def get_lr_stat_action_count(obj_identifier, stats_action):
    """
    Returns the count of the given stats action for the given resource instance.
    
    The obj_identifier is the identifier from the storage object.
    """
    result = LRStats.objects.filter(lrid=obj_identifier, action=stats_action) \
        .aggregate(Sum('count'))['count__sum']
    # `result` may be None in case the filter doesn't match any LRStats for the
    # specified resource and action
    if result is not None:
        return result
    else:
        return 0


def get_lr_master_url(resource):
    """
    Returns the full URL of the master copy of the given resource object.
    
    This URL points to the single resource view of the resource on the resource'
    master node.
    """
    return "{0}/{1}".format(resource.storage_object.source_url,
                            resource.get_relative_url())
