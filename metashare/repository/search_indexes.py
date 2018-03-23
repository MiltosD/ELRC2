import logging
import os
import re
from metashare.repository.model_utils import is_processable
from unidecode import unidecode

from haystack.indexes import CharField, IntegerField, SearchIndex
from haystack import indexes, connections as haystack_connections, \
    connection_router as haystack_connection_router

from django.db.models import signals
from django.utils.translation import ugettext as _

from metashare.repository import model_utils
from metashare.repository.dataformat_choices import MIMETYPEVALUE_TO_MIMETYPELABEL
from metashare.repository.models import resourceInfoType_model, \
    corpusInfoType_model, \
    toolServiceInfoType_model, lexicalConceptualResourceInfoType_model, \
    languageDescriptionInfoType_model
from metashare.repository.search_fields import LabeledMultiValueField, LabeledCharField
from metashare.settings import LOG_HANDLER
from metashare.storage.models import StorageObject, INGESTED, PUBLISHED, INTERNAL
from metashare.stats.model_utils import DOWNLOAD_STAT, VIEW_STAT


# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)


def update_lr_index_entry(res_obj):
    """
    Updates/creates the search index entry for the given language resource
    object.
    
    The appropriate search index is automatically chosen.
    """
    router_name = haystack_connection_router.for_write()
    if hasattr(router_name, '__iter__'):
        router_name = router_name[0]
    haystack_connections[router_name] \
        .get_unified_index().get_index(resourceInfoType_model) \
        .update_object(res_obj)

# pylint: disable-msg=C0103
class resourceInfoType_modelIndex(SearchIndex, indexes.Indexable):
    """
    The `SearchIndex` which indexes `resourceInfoType_model`s.
    """
    # in the text field we list all resource model field that shall be searched
    # search fields are defined in templates/search/indexes/repository/resourceinfotype_model_text.txt 
    text = CharField(document=True, use_template=True, stored=False)

    # view and download counts of the resource
    dl_count = IntegerField(stored=False)
    view_count = IntegerField(stored=False)

    # list of sorting results
    # the access to the sorting results is made in the MetashareFacetedSearchView function of views.py
    resourceNameSort = CharField(indexed=True, faceted=True)
    resourceTypeSort = CharField(indexed=True, faceted=True)
    mediaTypeSort = CharField(indexed=True, faceted=True)
    languageNameSort = CharField(indexed=True, faceted=True)

    # list of filters
    #
    # filter fields are described using:
    #   - label: the display of the filter in the interface,
    #   - facet_id: a unique id per filter,
    #   - parent_id: used for sub filters, indicates which filter is the parent of a sub filter
    #       (parent_id=0 is mandatory for top filters)
    #   - faceted=True: mandatory to indicate the field is a filter
    #
    # notice: variable names must end by "Filter"
    #
    # important notice: the definition of the variable name is important for sub filters:
    #   The item name of the sub filter must be lower cased for (e.g. textngram),
    #     then followed by the sub filter name with the first character upper cased (e.g. textngramOrder),
    #     and finalised with "Filter" (e.g. textngramOrderFilter). Otherwise, another item of the same top filter
    #     could be considered as parent (here, for instance, "text" instead of "textngram")
    #
    # for each filter, a facet function must be added to "SearchQuerySet()" in urls.py
    #   (e.g. .facet("textngramOrderFilter"), the function parameter corresponding to the variable name of the filter
    #
    # the creation of the filter structure is made in the _create_filters_structure function of views.py
    languageNameFilter = LabeledMultiValueField(
        label=_('Language'), facet_id=1, parent_id=0,
        faceted=True)
    resourceTypeFilter = LabeledMultiValueField(
        label=_('Resource Type'), facet_id=2, parent_id=0,
        faceted=True)
    mediaTypeFilter = LabeledMultiValueField(
        label=_('Media Type'), facet_id=3, parent_id=0,
        faceted=True)
    # availabilityFilter = LabeledMultiValueField(
    #     label=_('Availability'), facet_id=4, parent_id=0,
    #     faceted=True)
    licenceFilter = LabeledMultiValueField(
        label=_('Licence'), facet_id=5, parent_id=0,
        faceted=True)
    restrictionsOfUseFilter = LabeledMultiValueField(
        label=_('Conditions of Use'), facet_id=6, parent_id=0,
        faceted=True)
    validatedFilter = LabeledMultiValueField(
        label=_('Validated'), facet_id=7, parent_id=0,
        faceted=True)
    useNlpSpecificFilter = LabeledMultiValueField(
        label=_('Use Is NLP Specific'), facet_id=9, parent_id=0,
        faceted=True)
    lingualityTypeFilter = LabeledMultiValueField(
        label=_('Linguality Type'), facet_id=10, parent_id=0,
        faceted=True)
    multilingualityTypeFilter = LabeledMultiValueField(
        label=_('Multilinguality Type'), facet_id=11, parent_id=0,
        faceted=True)
    modalityTypeFilter = LabeledMultiValueField(
        label=_('Modality Type'), facet_id=12, parent_id=0,
        faceted=True)
    dataFormatFilter = LabeledMultiValueField(
        label=_('Data Format'), facet_id=13, parent_id=0,
        faceted=True)
    # bestPracticesFilter = LabeledMultiValueField(
    #     label=_('Conformance to Standards/Best Practices'), facet_id=14, parent_id=0,
    #     faceted=True)
    domainFilter = LabeledMultiValueField(
        label=_('Domain'), facet_id=15, parent_id=0,
        faceted=True)
    corpusAnnotationTypeFilter = LabeledMultiValueField(
        label=_('Annotation Type'), facet_id=19, parent_id=2,
        faceted=True)
    languageDescriptionLDTypeFilter = LabeledMultiValueField(
        label=_('Language Description Type'), facet_id=21, parent_id=2,
        faceted=True)
    languageDescriptionEncodingLevelFilter = LabeledMultiValueField(
        label=_('Encoding Level'), facet_id=22, parent_id=2,
        faceted=True)
    languageDescriptionGrammaticalPhenomenaCoverageFilter = LabeledMultiValueField(
        label=_('Grammatical Phenomena Coverage'), facet_id=23, parent_id=2,
        faceted=True)
    lexicalConceptualResourceLRTypeFilter = LabeledMultiValueField(
        label=_('Lexical/Conceptual Resource Type'), facet_id=24, parent_id=2,
        faceted=True)
    lexicalConceptualResourceEncodingLevelFilter = LabeledMultiValueField(
        label=_('Encoding Level'), facet_id=25, parent_id=2,
        faceted=True)
    lexicalConceptualResourceLinguisticInformationFilter = LabeledMultiValueField(
        label=_('Linguistic Information'), facet_id=26, parent_id=2,
        faceted=True)

    toolServiceToolServiceTypeFilter = LabeledMultiValueField(
        label=_('Tool/Service Type'), facet_id=27, parent_id=2,
        faceted=True)
    toolServiceToolServiceSubTypeFilter = LabeledMultiValueField(
        label=_('Tool/Service Subtype'), facet_id=28, parent_id=2,
        faceted=True)
    toolServiceLanguageDependentTypeFilter = LabeledMultiValueField(
        label=_('Language Dependent'), facet_id=29, parent_id=2,
        faceted=True)
    toolServiceInputOutputResourceTypeFilter = LabeledMultiValueField(
        label=_('InputInfo/OutputInfo Resource Type'), facet_id=30, parent_id=2,
        faceted=True)
    toolServiceInputOutputMediaTypeFilter = LabeledMultiValueField(
        label=_('InputInfo/OutputInfo Media Type'), facet_id=31, parent_id=2,
        faceted=True)
    toolServiceAnnotationTypeFilter = LabeledMultiValueField(
        label=_('Annotation Type'), facet_id=32, parent_id=2,
        faceted=True)
    # toolServiceAnnotationFormatFilter = LabeledMultiValueField(
    #     label=_('Annotation Format'), facet_id=33, parent_id=2,
    #     faceted=True)
    # toolServiceEvaluatedFilter = LabeledMultiValueField(
    #     label=_('Evaluated'), facet_id=34, parent_id=2,
    #     faceted=True)
    appropriatenessForDSIFilter = LabeledMultiValueField(
        label=_('Appropriateness For DSI'), facet_id=56, parent_id=0,
        faceted=True)

    publicationStatusFilter = LabeledCharField(
        label=_('Publication Status'), facet_id=57, parent_id=0,
        faceted=True)

    processabilityFilter = LabeledCharField(
        label=_('Processable by ELRC'), facet_id=58, parent_id=0,
        faceted=True)

    # Start sub filters
    textTextGenreFilter = LabeledMultiValueField(
        label=_('Text Genre'), facet_id=35, parent_id=3,
        faceted=True)
    textTextTypeFilter = LabeledMultiValueField(
        label=_('Text Type'), facet_id=36, parent_id=3,
        faceted=True)
    # languageVarietyFilter = LabeledMultiValueField(
    #     label=_('Language Variety'), facet_id=55, parent_id=0,
    #     faceted=True)

    # we create all items that may appear in the search results list already at
    # index time
    rendered_result = CharField(use_template=True, indexed=False)

    def get_model(self):
        """
        Returns the model class of which instances are indexed here.
        """
        return resourceInfoType_model

    def index_queryset(self, using=None):
        """
        Returns the default QuerySet to index when doing a full index update.

        In our case this is a QuerySet containing only published resources that
        have not been deleted, yet.
        """
        return self.read_queryset()

    def read_queryset(self, using=None):
        """
        Returns the default QuerySet for read actions.

        In our case this is a QuerySet containing only published resources that
        have not been deleted, yet.
        """
        return self.get_model().objects.filter(storage_object__deleted=False,
                                               storage_object__publication_status__in=[INGESTED, PUBLISHED])

    def should_update(self, instance, **kwargs):
        '''
        Only index resources that are at least ingested.
        In other words, do not index internal resources.
        '''
        return instance.storage_object.publication_status in (INGESTED, PUBLISHED)

    def update_object(self, instance, using=None, **kwargs):
        """
        Updates the index for a single object instance.

        In this implementation we do not only handle instances of the model as
        returned by get_model(), but we also support the models that are
        registered in our own _setup_save() method.
        """
        if os.environ.get('DISABLE_INDEXING_DURING_IMPORT', False) == 'True':
            return

        if isinstance(instance, StorageObject):
            LOGGER.debug("StorageObject changed for resource #{0}." \
                         .format(instance.id))
            related_resource_qs = instance.resourceinfotype_model_set
            if (not related_resource_qs.count()):
                # no idea why this happens, but it does; there are storage
                # objects which are not attached to any
                # resourceInfoType_model
                return
            related_resource = related_resource_qs.iterator().next()
            if instance.deleted:
                # if the resource has been flagged for deletion, then we
                # don't want to keep/have it in the index
                LOGGER.info("Resource #{0} scheduled for deletion from " \
                            "the index.".format(related_resource.id))
                self.remove_object(related_resource, using=using)
                return
            instance = related_resource
        elif not isinstance(instance, self.get_model()):
            assert False, "Unexpected sender: {0}".format(instance)
            LOGGER.error("Unexpected sender: {0}".format(instance))
            return

        # we better recreate our resource instance from the DB as otherwise it
        # has happened for some reason that the instance was not up-to-date
        instance = self.get_model().objects.get(pk=instance.id)
        LOGGER.info("Resource #{0} scheduled for reindexing." \
                    .format(instance.id))
        super(resourceInfoType_modelIndex, self) \
            .update_object(instance, using=using, **kwargs)

    def remove_object(self, instance, using=None, **kwargs):
        """
        Removes a single object instance from the index.
        """
        if os.environ.get('DISABLE_INDEXING_DURING_IMPORT', False) == 'True':
            return

        super(resourceInfoType_modelIndex, self).remove_object(instance,
                                                               using=using,
                                                               **kwargs)

    def prepare_dl_count(self, obj):
        """
        Returns the download count for the given resource object.
        """
        return model_utils.get_lr_stat_action_count(
            obj.storage_object.identifier, DOWNLOAD_STAT)

    def prepare_view_count(self, obj):
        """
        Returns the view count for the given resource object.
        """
        return model_utils.get_lr_stat_action_count(
            obj.storage_object.identifier, VIEW_STAT)

    def prepare_resourceNameSort(self, obj):
        """
        Collect the data to sort the Resource Names
        """
        # get the Resource Name
        resourceNameSort = obj.identificationInfo.get_default_resourceName()
        resourceNameSort = unidecode(resourceNameSort)
        # keep alphanumeric characters only
        resourceNameSort = re.sub('[\W_]', '', resourceNameSort)
        # set Resource Name to lower case
        resourceNameSort = resourceNameSort.lower()

        return resourceNameSort

    def prepare_resourceTypeSort(self, obj):
        """
        Collect the data to sort the Resource Types
        """
        # get the list of Resource Types
        resourceTypeSort = self.prepare_resourceTypeFilter(obj)
        # render unique list of Resource Types
        resourceTypeSort = list(set(resourceTypeSort))
        # sort Resource Types
        resourceTypeSort.sort()
        # join Resource Types into a string
        resourceTypeSort = ",".join(resourceTypeSort)
        # keep alphanumeric characters only
        resourceTypeSort = re.sub('[\W_]', '', resourceTypeSort)
        # set list of Resource Types to lower case
        resourceTypeSort = resourceTypeSort.lower()

        return resourceTypeSort

    def prepare_mediaTypeSort(self, obj):
        """
        Collect the data to sort the Media Types
        """
        # get the list of Media Types
        mediaTypeSort = self.prepare_mediaTypeFilter(obj)
        # render unique list of Media Types
        mediaTypeSort = list(set(mediaTypeSort))
        # sort Media Types
        mediaTypeSort.sort()
        # join Media Types into a string
        mediaTypeSort = ",".join(mediaTypeSort)
        # keep alphanumeric characters only
        mediaTypeSort = re.sub('[\W_]', '', mediaTypeSort)
        # set list of Media Types to lower case
        mediaTypeSort = mediaTypeSort.lower()

        return mediaTypeSort

    def prepare_languageNameSort(self, obj):
        """
        Collect the data to sort the Language Names
        """
        # get the list of languages
        languageNameSort = self.prepare_languageNameFilter(obj)
        # render unique list of languages
        languageNameSort = list(set(languageNameSort))
        # sort languages
        languageNameSort.sort()
        # join languages into a string
        languageNameSort = ",".join(languageNameSort)
        # keep alphanumeric characters only
        languageNameSort = re.sub('[\W_]', '', languageNameSort)
        # set list of languages to lower case
        languageNameSort = languageNameSort.lower()

        return languageNameSort

    def prepare_languageNameFilter(self, obj):
        """
        Collect the data to filter the resources on Language Name
        """
        result = []
        corpus_media = obj.resourceComponentType.as_subclass()

        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                result.extend([lang.languageName for lang in
                               corpus_info.languageinfotype_model_set.all()])

        elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
            if lcr_media_type.lexicalConceptualResourceTextInfo:
                result.extend([lang.languageName for lang in lcr_media_type \
                              .lexicalConceptualResourceTextInfo.languageinfotype_model_set.all()])

        elif isinstance(corpus_media, languageDescriptionInfoType_model):
            ld_media_type = corpus_media.languageDescriptionMediaType
            if ld_media_type.languageDescriptionTextInfo:
                result.extend([lang.languageName for lang in ld_media_type \
                              .languageDescriptionTextInfo.languageinfotype_model_set.all()])

        elif isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.inputInfo:
                result.extend([lang.languageName for lang in
                               corpus_media.inputInfo.languagesetinfotype_model_set.all()])
            if corpus_media.outputInfo:
                result.extend([lang.languageName for lang in
                               corpus_media.outputInfo.languagesetinfotype_model_set.all()])

        return result

    def prepare_resourceTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type
        """
        resType = obj.resourceComponentType.as_subclass().resourceType
        if resType:
            return [resType]
        return []

    def prepare_mediaTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Media Type
        """
        return model_utils.get_resource_media_types(obj)

    def prepare_availabilityFilter(self, obj):
        """
        Collect the data to filter the resources on Availability
        """
        return [distributionInfo.get_availability_display()
                for distributionInfo in obj.distributioninfotype_model_set.all()]

    def prepare_licenceFilter(self, obj):
        """
        Collect the data to filter the resources on Licence
        """
        return model_utils.get_resource_license_types(obj)

    def prepare_restrictionsOfUseFilter(self, obj):
        """
        Collect the data to filter the resources on Restrictions Of USe
        """
        return [restr for distributionInfo in obj.distributioninfotype_model_set.all()
                for licence_info in
                distributionInfo.licenceInfo.all()
                for restr in licence_info.get_restrictionsOfUse_display_list()]

    def prepare_validatedFilter(self, obj):
        """
        Collect the data to filter the resources on Validated
        """
        return [validation_info.validated for validation_info in
                obj.validationinfotype_model_set.all()]

    def prepare_lingualityTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Linguality Type
        """
        return model_utils.get_resource_linguality_infos(obj)

    def prepare_multilingualityTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Multilinguality Type
        """
        result = []
        corpus_media = obj.resourceComponentType.as_subclass()

        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                mtf = corpus_info.lingualityInfo \
                    .get_multilingualityType_display()
                if mtf != '':
                    result.append(mtf)

        elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
            if lcr_media_type.lexicalConceptualResourceTextInfo:
                mtf = lcr_media_type.lexicalConceptualResourceTextInfo \
                    .lingualityInfo.get_multilingualityType_display()
                if mtf != '':
                    result.append(mtf)

        elif isinstance(corpus_media, languageDescriptionInfoType_model):
            ld_media_type = corpus_media.languageDescriptionMediaType
            if ld_media_type.languageDescriptionTextInfo:
                mtf = ld_media_type.languageDescriptionTextInfo \
                    .lingualityInfo.get_multilingualityType_display()
                if mtf != '':
                    result.append(mtf)

        return result

    def prepare_dataFormatFilter(self, obj):
        """
        Collect the data to filter the resources on Mime Type
        """
        dataFormat_list = []
        corpus_media = obj.resourceComponentType.as_subclass()

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

    def prepare_bestPracticesFilter(self, obj):
        """
        Collect the data to filter the resources on Best Practices
        """
        result = []
        corpus_media = obj.resourceComponentType.as_subclass()

        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                for annotation_info in corpus_info.annotationinfotype_model_set.all():
                    result.extend(annotation_info.get_conformanceToStandardsBestPractices_display_list())

        elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            if corpus_media.lexicalConceptualResourceEncodingInfo:
                result.extend(corpus_media.lexicalConceptualResourceEncodingInfo \
                              .get_conformanceToStandardsBestPractices_display_list())

        elif isinstance(corpus_media, languageDescriptionInfoType_model):
            if corpus_media.languageDescriptionEncodingInfo:
                result.extend(corpus_media.languageDescriptionEncodingInfo \
                              .get_conformanceToStandardsBestPractices_display_list())

        elif isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.inputInfo:
                result.extend(corpus_media.inputInfo \
                              .get_conformanceToStandardsBestPractices_display_list())
            if corpus_media.outputInfo:
                result.extend(corpus_media.outputInfo \
                              .get_conformanceToStandardsBestPractices_display_list())

        return result

    def prepare_domainFilter(self, obj):
        """
        Collect the data to filter the resources on Domain
        """
        result = []
        corpus_media = obj.resourceComponentType.as_subclass()

        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                result.extend([domain_info.domain for domain_info in
                               corpus_info.domaininfotype_model_set.all()])

        elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
            if lcr_media_type.lexicalConceptualResourceTextInfo:
                result.extend([domain_info.domain for domain_info in
                               lcr_media_type.lexicalConceptualResourceTextInfo \
                              .domaininfotype_model_set.all()])

        elif isinstance(corpus_media, languageDescriptionInfoType_model):
            ld_media_type = corpus_media.languageDescriptionMediaType
            if ld_media_type.languageDescriptionTextInfo:
                result.extend([domain_info.domain for domain_info in
                               ld_media_type.languageDescriptionTextInfo \
                              .domaininfotype_model_set.all()])

        return result

    def prepare_corpusAnnotationTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for corpus
        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                for annotation_info in corpus_info.annotationinfotype_model_set.all():
                    result.append(annotation_info.get_annotationType_display())

        return result

    def prepare_languageDescriptionLDTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        corpus_media = obj.resourceComponentType.as_subclass()
        if isinstance(corpus_media, languageDescriptionInfoType_model):
            return [corpus_media.get_languageDescriptionType_display()]
        return []

    def prepare_languageDescriptionEncodingLevelFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        corpus_media = obj.resourceComponentType.as_subclass()
        if isinstance(corpus_media, languageDescriptionInfoType_model) \
                and corpus_media.languageDescriptionEncodingInfo:
            return corpus_media.languageDescriptionEncodingInfo \
                .get_encodingLevel_display_list()
        return []

    def prepare_lexicalConceptualResourceLRTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for lexicalConceptual
        if isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            result.append(corpus_media.get_lexicalConceptualResourceType_display())

        return result

    def prepare_lexicalConceptualResourceEncodingLevelFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for lexicalConceptual
        if isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            if corpus_media.lexicalConceptualResourceEncodingInfo:
                result.extend(corpus_media.lexicalConceptualResourceEncodingInfo. \
                              get_encodingLevel_display_list())

        return result

    def prepare_lexicalConceptualResourceLinguisticInformationFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for lexicalConceptual
        if isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            if corpus_media.lexicalConceptualResourceEncodingInfo:
                result.extend(corpus_media.lexicalConceptualResourceEncodingInfo. \
                              get_linguisticInformation_display_list())

        return result

    def prepare_toolServiceToolServiceTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for toolService
        if isinstance(corpus_media, toolServiceInfoType_model):
            result.append(corpus_media.get_toolServiceType_display())

        return result

    # TODO: edit to Function field
    # def prepare_toolServiceToolServiceSubTypeFilter(self, obj):
    #     """
    #     Collect the data to filter the resources on Resource Type children
    #     """
    #     result = []
    #
    #     corpus_media = obj.resourceComponentType.as_subclass()
    #
    #     # Filter for toolService
    #     if isinstance(corpus_media, toolServiceInfoType_model):
    #         result.extend(corpus_media.toolServiceSubtype)
    #
    #     return result

    def prepare_toolServiceLanguageDependentTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for toolService
        if isinstance(corpus_media, toolServiceInfoType_model):
            result.append(corpus_media.get_languageDependent_display())

        return result

    def prepare_toolServiceInputOutputResourceTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for toolService
        if isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.inputInfo:
                result.extend(
                    corpus_media.inputInfo.get_resourceType_display_list())
            if corpus_media.outputInfo:
                result.extend(
                    corpus_media.outputInfo.get_resourceType_display_list())

        return result

    def prepare_toolServiceInputOutputMediaTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for toolService
        if isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.inputInfo:
                result.append(corpus_media.inputInfo.get_mediaType_display())
            if corpus_media.outputInfo:
                result.append(corpus_media.outputInfo.get_mediaType_display())

        return result

    def prepare_toolServiceAnnotationTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        if isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.inputInfo:
                result.extend(corpus_media.inputInfo.get_annotationType_display_list())
            if corpus_media.outputInfo:
                result.extend(corpus_media.outputInfo.get_annotationType_display_list())

        return result

    def prepare_toolServiceEvaluatedFilter(self, obj):
        """
        Collect the data to filter the resources on Resource Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for toolService
        if isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.toolServiceEvaluationInfo:
                result.append(corpus_media.toolServiceEvaluationInfo.get_evaluated_display())

        return result

    def prepare_textTextGenreFilter(self, obj):
        """
        Collect the data to filter the resources on Media Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for corpus
        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                result.extend([text_classification_info.textGenre \
                               for text_classification_info in corpus_info.textclassificationinfotype_model_set.all()])

        return result

    def prepare_textTextTypeFilter(self, obj):
        """
        Collect the data to filter the resources on Media Type children
        """
        result = []

        corpus_media = obj.resourceComponentType.as_subclass()

        # Filter for corpus
        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                result.extend([text_classification_info.textType \
                               for text_classification_info in corpus_info.textclassificationinfotype_model_set.all()])

        return result

    def prepare_languageVarietyFilter(self, obj):
        """
        Collect the data to filter the resources on Language Variety
        """
        result = []
        corpus_media = obj.resourceComponentType.as_subclass()

        if isinstance(corpus_media, corpusInfoType_model):
            media_type = corpus_media.corpusMediaType
            for corpus_info in media_type.corpustextinfotype_model_set.all():
                for lang in corpus_info.languageinfotype_model_set.all():
                    result.extend([variety.languageVarietyName for variety in
                                   lang.languageVarietyInfo.all()])

        elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
            lcr_media_type = corpus_media.lexicalConceptualResourceMediaType
            if lcr_media_type.lexicalConceptualResourceTextInfo:
                for lang in lcr_media_type.lexicalConceptualResourceTextInfo. \
                        languageinfotype_model_set.all():
                    result.extend([variety.languageVarietyName for variety in
                                   lang.languageVarietyInfo.all()])

        elif isinstance(corpus_media, languageDescriptionInfoType_model):
            ld_media_type = corpus_media.languageDescriptionMediaType
            if ld_media_type.languageDescriptionTextInfo:
                for lang in ld_media_type.languageDescriptionTextInfo. \
                        languageinfotype_model_set.all():
                    result.extend([variety.languageVarietyName for variety in
                                   lang.languageVarietyInfo.all()])

        elif isinstance(corpus_media, toolServiceInfoType_model):
            if corpus_media.inputInfo:
                result.extend(corpus_media.inputInfo.languageVarietyName)
            if corpus_media.outputInfo:
                result.extend(corpus_media.outputInfo.languageVarietyName)

        return result

    def prepare_appropriatenessForDSIFilter(self, obj):
        """
        Collect the data to filter the resources on appropriatenessForDSIFilter
        """
        return obj.identificationInfo.get_appropriatenessForDSI_display_list()

    def prepare_publicationStatusFilter(self, obj):
        """
        Collect the data to filter the resources on publication status
        """
        return obj.publication_status()

    def prepare_processabilityFilter(self, obj):
        return is_processable(obj)
