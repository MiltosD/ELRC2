# pylint: disable-msg=C0302
import logging
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.deletion import ProtectedError
from django.template.defaultfilters import slugify

from metashare.eurovoc import eurovoc
from metashare.bcp47 import iana

from metashare.accounts.models import EditorGroup
# pylint: disable-msg=W0611
from metashare.repository.supermodel import SchemaModel, SubclassableModel, \
    _make_choices_from_list, _make_choices_from_int_list, \
    REQUIRED, OPTIONAL, RECOMMENDED
from metashare.repository.editor.widgets import MultiFieldWidget, MultiChoiceWidget
from metashare.repository.fields import MultiTextField, MetaBooleanField, \
    MultiSelectField, DictField, XmlCharField, best_lang_value_retriever
from metashare.repository.validators import validate_lang_code_keys, \
    validate_dict_values, validate_xml_schema_year, \
    validate_matches_xml_char_production, validate_size_is_integer, validate_attribution_text
from metashare.settings import DJANGO_BASE, LOG_HANDLER, DJANGO_URL
from metashare.stats.model_utils import saveLRStats, DELETE_STAT, UPDATE_STAT
from metashare.storage.models import StorageObject, MASTER, COPY_CHOICES
from metashare.recommendations.models import ResourceCountPair, \
    ResourceCountDict
# from metashare.repository.language_choices import LANGUAGENAME_CHOICES
from metashare.repository.dataformat_choices import TEXTFORMATINFOTYPE_DATAFORMAT_CHOICES

# MIMETYPELABEL_TO_MIMETYPEVALUE

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)

# Note: we have to use the '^' and '$' anchors in the following regular
# expressions as for some reason the RegexValidator does not try to match the
# whole string against the regex but it just searches for a matching substring;
# in addition we have to use the negative lookahead assertion at the end of the
# regular expressions as Python's regex engine otherwise always ignores a single
# trailing newline
EMAILADDRESS_VALIDATOR = RegexValidator(r'^[^@]+@[^\.]+\..+(?!\r?\n)$',
                                        'Not a valid emailAddress value.', ValidationError)
HTTPURI_VALIDATOR = RegexValidator(r"^(?i)((http|ftp)s?):\/\/"
                                   r"(([a-z0-9.-]|%[0-9A-F]{2}){3,})(:(\d+))?"
                                   r"((\/([a-z0-9-._~!$&'()*+,;=:@]|%[0-9A-F]{2})*)*)"
                                   r"(\?(([a-z0-9-._~!$&'()*+,;=:\/?@]|%[0-9A-F]{2})*))?"
                                   r"(#(([a-z0-9-._~!$&'()*+,;=:\/?@]|%[0-9A-F]{2})*))?(?!\r?\n)$",
                                   "Not a valid URL value (must not contain non-ASCII characters, for example;"
                                   " see also RFC 2396).", ValidationError)

# namespace of the META-SHARE metadata XML Schema
SCHEMA_NAMESPACE = 'http://www.elrc-share.eu/ELRC-SHARE_SCHEMA/v2.0/'
# version of the META-SHARE metadata XML Schema
SCHEMA_VERSION = '2.0'


def country_optgroup_choices():
    """
    Group the choices in groups. The first group the EU languages
    and the second group contains the rest.
    """
    eu_choices = ('EU', _make_choices_from_list(iana.get_eu_regions())['choices'])
    more_choices = ('More', _make_choices_from_list(sorted(iana.get_rest_of_regions()))['choices'])
    optgroup = [eu_choices, more_choices]
    return optgroup


# pylint: disable-msg=C0103
class resourceInfoType_model(SchemaModel):
    """
    Groups together all information required for the description of
    language resources
    """

    class Meta:
        verbose_name = "Resource"

    __schema_name__ = 'resourceInfo'
    __schema_fields__ = (
        (u'identificationInfo', u'identificationInfo', REQUIRED),
        (u'distributionInfo', u'distributioninfotype_model_set', REQUIRED),
        (u'contactPerson', u'contactPerson', REQUIRED),
        (u'metadataInfo', u'metadataInfo', REQUIRED),
        (u'versionInfo', u'versionInfo', RECOMMENDED),
        (u'resourceCreationInfo', u'resourceCreationInfo', RECOMMENDED),
        (u'resourceDocumentationInfo', u'resourceDocumentationInfo', RECOMMENDED),
        (u'validationInfo', u'validationinfotype_model_set', RECOMMENDED),
        (u'relationInfo', u'relationinfotype_model_set', RECOMMENDED),
        ('resourceComponentType/corpusInfo', 'resourceComponentType', REQUIRED),
        ('resourceComponentType/toolServiceInfo', 'resourceComponentType', REQUIRED),
        ('resourceComponentType/languageDescriptionInfo', 'resourceComponentType', REQUIRED),
        ('resourceComponentType/lexicalConceptualResourceInfo', 'resourceComponentType', REQUIRED),
    )
    __schema_classes__ = {
        u'contactPerson': "personInfoType_model",
        u'corpusInfo': "corpusInfoType_model",
        u'distributionInfo': "distributionInfoType_model",
        u'identificationInfo': "identificationInfoType_model",
        u'languageDescriptionInfo': "languageDescriptionInfoType_model",
        u'lexicalConceptualResourceInfo': "lexicalConceptualResourceInfoType_model",
        u'metadataInfo': "metadataInfoType_model",
        u'relationInfo': "relationInfoType_model",
        u'resourceCreationInfo': "resourceCreationInfoType_model",
        u'resourceDocumentationInfo': "resourceDocumentationInfoType_model",
        u'toolServiceInfo': "toolServiceInfoType_model",
        u'validationInfo': "validationInfoType_model",
        u'versionInfo': "versionInfoType_model",
    }

    identificationInfo = models.OneToOneField("identificationInfoType_model",
                                              verbose_name='Identification',
                                              help_text='Groups together information needed to identify the reso' \
                                                        'urce',
                                              )

    # OneToMany field: distributionInfo

    contactPerson = models.ManyToManyField("personInfoType_model",
                                           verbose_name='Contact person',
                                           help_text='Groups information on the person(s) that is/are respons' \
                                                     'ible for providing further information regarding the resource',
                                           related_name="contactPerson_%(class)s_related", )

    metadataInfo = models.OneToOneField("metadataInfoType_model",
                                        verbose_name='Metadata',
                                        help_text='Groups information on the metadata record itself',
                                        )

    versionInfo = models.OneToOneField("versionInfoType_model",
                                       verbose_name='Version',
                                       help_text='Groups information on a specific version or release of ' \
                                                 'the resource',
                                       blank=True, null=True, on_delete=models.SET_NULL, )

    resourceCreationInfo = models.OneToOneField("resourceCreationInfoType_model",
                                                verbose_name='Resource creation',
                                                help_text='Groups information on the creation procedure of a resou' \
                                                          'rce',
                                                blank=True, null=True, on_delete=models.SET_NULL, )

    resourceDocumentationInfo = models.OneToOneField("resourceDocumentationInfoType_model",
                                                     verbose_name='Resource documentation',
                                                     help_text='Groups together information on any document describing ' \
                                                               'the resource',
                                                     blank=True, null=True, on_delete=models.SET_NULL, )

    # OneToMany field: validationInfo

    # OneToMany field: relationInfo

    resourceComponentType = models.OneToOneField("resourceComponentTypeType_model",
                                                 verbose_name='Resource component type',
                                                 help_text='Used for distinguishing between resource types',
                                                 )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['identificationInfo/resourceName', ]
        formatstring = u'{}'
        return self.unicode_(formatstring, formatargs)

    editor_groups = models.ManyToManyField(EditorGroup, blank=True)

    owners = models.ManyToManyField(User, blank=True)

    storage_object = models.ForeignKey(StorageObject, blank=True, null=True,
                                       unique=True)

    def save(self, *args, **kwargs):
        """
        Overrides the predefined save() method to ensure that a corresponding
        StorageObject instance is existing, creating it if missing.  Also, we
        check that the storage object instance is a local master copy.
        """
        # If we have not yet created a StorageObject for this resource, do so.
        if not self.storage_object:
            self.storage_object = StorageObject.objects.create(
                metadata='<NOT_READY_YET/>')

        # Check that the storage object instance is a local master copy.
        if not self.storage_object.master_copy:
            LOGGER.warning('Trying to modify non master copy {0}, ' \
                           'aborting!'.format(self.storage_object))
            return

        self.storage_object.save()
        # REMINDER: the SOLR indexer in search_indexes.py relies on us
        # calling storage_object.save() from resourceInfoType_model.save().
        # Should we ever change that, we must modify
        # resourceInfoType_modelIndex._setup_save() accordingly!

        # get the resource description languages
        resource_lang = list(self.identificationInfo.description.iterkeys())

        # Call save() method from super class with all arguments.
        super(resourceInfoType_model, self).save(*args, **kwargs)

        # get the metadataInfo and update the languages to match the description
        # languages
        self.metadataInfo.save(langs=resource_lang)

        # update statistics
        saveLRStats(self, UPDATE_STAT)

    def has_relations(self):
        """
        Return True is if resource has relations
        """
        # check the resource has no relation to other non-deleted resource
        if self.relationinfotype_model_set.all():
            return True
        return False

    def delete(self, keep_stats=False, *args, **kwargs):
        """
        Overrides the predefined delete() method to update the statistics.
        Includes deletion of statistics; use keep_stats optional parameter to
        suppress deletion of statistics
        """
        if self.has_relations():
            raise ProtectedError(
                protected_objects=self,
                msg="Cannot delete this resource because it has relations to other resources")
        if not keep_stats:
            # delete statistics
            saveLRStats(self, DELETE_STAT)
            # delete recommendations
            ResourceCountPair.objects.filter(lrid=self.storage_object.identifier).delete()
            ResourceCountDict.objects.filter(lrid=self.storage_object.identifier).delete()

        # Call delete() method from super class with all arguments but keep_stats
        super(resourceInfoType_model, self).delete(*args, **kwargs)

    def get_absolute_url(self):
        return '/{0}{1}'.format(DJANGO_BASE, self.get_relative_url())

    def get_relative_url(self):
        """
        Returns part of the complete URL which resembles the single resource
        view for this resource.

        The returned part prepended with a '/' can be appended to `DJANGO_URL`
        in order to get the complete URL.
        """
        return 'repository/browse/{}/{}/'.format(slugify(self.__unicode__()),
                                                 self.storage_object.identifier)

    def publication_status(self):
        """
        Method used for changelist view for resources.
        """
        storage_object = getattr(self, 'storage_object', None)
        if storage_object:
            return storage_object.get_publication_status_display()

        return ''

    def resource_type(self):
        """
        Method used for changelist view for resources.
        """
        resource_component = getattr(self, 'resourceComponentType', None)
        if not resource_component:
            return None

        return resource_component.as_subclass()._meta.verbose_name


SIZEINFOTYPE_SIZEUNIT_CHOICES = _make_choices_from_list([
    u'terms', u'entries', u'files', u'items', u'texts', u'sentences',
    u'bytes', u'tokens', u'words', u'keywords', u'idiomaticExpressions',
    u'neologisms', u'multiWordUnits', u'expressions', u'concepts',
    u'lexicalTypes', u'kb', u'mb', u'gb', u'rules', u'translationUnits',
    u'phrases', u'segments', u'other',
])


# pylint: disable-msg=C0103
class sizeInfoType_model(SchemaModel):
    """
    Groups information on the size of the resource or of resource parts
    """

    class Meta:
        verbose_name = "Size"

    __schema_name__ = 'sizeInfoType'
    __schema_fields__ = (
        (u'size', u'size', REQUIRED),
        (u'sizeUnit', u'sizeUnit', REQUIRED),
    )

    size = XmlCharField(
        verbose_name='Size',
        help_text='Specifies the size of the resource with regard to the S' \
                  'izeUnit measurement in form of a number',
        max_length=100, validators=[validate_size_is_integer])

    sizeUnit = models.CharField(
        verbose_name='Size unit',
        help_text='Specifies the unit that is used when providing informat' \
                  'ion on the size of the resource or of resource parts',

        max_length=30,
        choices=sorted(SIZEINFOTYPE_SIZEUNIT_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    back_to_languagedescriptiontextinfotype_model = models.ForeignKey("languageDescriptionTextInfoType_model",
                                                                      blank=True, null=True)

    back_to_lexicalconceptualresourcetextinfotype_model = models.ForeignKey(
        "lexicalConceptualResourceTextInfoType_model", blank=True, null=True)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['size', 'sizeUnit', ]
        formatstring = u'{} {}'
        return self.unicode_(formatstring, formatargs)


IDENTIFICATIONINFOTYPE_APPROPRIATENESSFORDSI_CHOICES = _make_choices_from_list([
    u'OnlineDisputeResolution', u'Europeana', u'OpenDataPortal', u'eJustice',
    u'ElectronicExchangeOfSocialSecurityInformation', u'saferInternet',
    u'Cybersecurity', u'eHealth', u'eProcurement',
    u'BusinessRegistersInterconnectionSystem',
])


# pylint: disable-msg=C0103
class identificationInfoType_model(SchemaModel):
    """
    Groups together information needed to identify the resource
    """

    class Meta:
        verbose_name = "Identification"

    __schema_name__ = 'identificationInfoType'
    __schema_fields__ = (
        (u'resourceName', u'resourceName', REQUIRED),
        (u'description', u'description', REQUIRED),
        (u'resourceShortName', u'resourceShortName', OPTIONAL),
        (u'url', u'url', RECOMMENDED),
        (u'metaShareId', u'metaShareId', OPTIONAL),
        (u'ISLRN', u'ISLRN', OPTIONAL),
        (u'identifier', u'identifier', OPTIONAL),
        (u'appropriatenessForDSI', u'appropriatenessForDSI', OPTIONAL),
    )

    resourceName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                             default_retriever=best_lang_value_retriever,
                             verbose_name='Resource name',
                             max_val_length=500,
                             help_text='The full name by which the resource is known; the eleme' \
                                       'nt can be repeated for the different language versions using the ' \
                                       '"lang" attribute to specify the language.',
                             )

    description = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                            default_retriever=best_lang_value_retriever,
                            verbose_name='Description',
                            max_val_length=10000,
                            help_text='Provides the description of the resource in prose; the ' \
                                      'element can be repeated for the different language versions using' \
                                      ' the "lang" attribute to specify the language.',
                            )

    resourceShortName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                                  default_retriever=best_lang_value_retriever,
                                  verbose_name='Resource short name',
                                  max_val_length=500,
                                  help_text='The short form (abbreviation, acronym etc.) used to ide' \
                                            'ntify the resource; the element can be repeated for the different' \
                                            ' language versions using the "lang" attribute to specify the lang' \
                                            'uage.',
                                  blank=True)

    url = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=0, attrs={'size': '250'}),
                         verbose_name='Landing page (URL)', validators=[HTTPURI_VALIDATOR],
                         help_text='A Web page that can be navigated to in a Web browser to' \
                                   ' gain access to the resource, its distributions and/or additional' \
                                   ' information',
                         blank=True, )

    metaShareId = XmlCharField(
        verbose_name='Meta-Share ID',
        help_text='An unambiguous referent to the resource within META-SHA' \
                  'RE; it reflects to the unique system id provided automatically by' \
                  ' the MetaShare software',
        blank=True, max_length=100, default="NOT_DEFINED", )

    ISLRN = XmlCharField(
        verbose_name='ISLRN',
        help_text='Reference to the unique ISLRN number of the resource; i' \
                  'f the resource has not been assigned an ISLRN yet, you may reques' \
                  't for one at: http://www.islrn.org/',
        blank=True, max_length=17, validators=[validate_matches_xml_char_production], )

    identifier = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=1, max_length=100),
                                verbose_name='Identifier',
                                help_text='Reference to a PID, DOI or an internal identifier used ' \
                                          'by the resource provider for the resource',
                                blank=True, validators=[validate_matches_xml_char_production], )

    appropriatenessForDSI = MultiSelectField(
        verbose_name='Appropriateness for DSI',
        help_text='Specifies whether the resource is appropriate for use i' \
                  'n one or more of the DSIs (Digital Service Infrastructures)',
        blank=True,
        max_length=1 + len(IDENTIFICATIONINFOTYPE_APPROPRIATENESSFORDSI_CHOICES['choices']) / 4,
        choices=IDENTIFICATIONINFOTYPE_APPROPRIATENESSFORDSI_CHOICES['choices'],
    )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class versionInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Version"

    __schema_name__ = 'versionInfoType'
    __schema_fields__ = (
        (u'version', u'version', REQUIRED),
        (u'lastDateUpdated', u'lastDateUpdated', OPTIONAL),
    )

    version = XmlCharField(
        verbose_name='Version',
        help_text='Any string, usually a number, that identifies the versi' \
                  'on of a resource',
        max_length=100, )

    lastDateUpdated = models.DateField(
        verbose_name='Last date updated',
        help_text='Date of the last update of the version of the resource',
        blank=True, null=True, )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['version', 'revision', 'lastDateUpdated', ]
        formatstring = u'{} {} {}'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class validationInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Validation"

    __schema_name__ = 'validationInfoType'
    __schema_fields__ = (
        (u'validated', u'validated', REQUIRED),
        ('validationReport/documentUnstructured', 'validationReport', OPTIONAL),
        ('validationReport/documentInfo', 'validationReport', OPTIONAL),
        ('validator/personInfo', 'validator', OPTIONAL),
        ('validator/organizationInfo', 'validator', OPTIONAL),
    )
    __schema_classes__ = {
        u'documentInfo': "documentInfoType_model",
        u'documentUnstructured': "documentUnstructuredString_model",
        u'organizationInfo': "organizationInfoType_model",
        u'personInfo': "personInfoType_model",
    }

    validated = MetaBooleanField(
        verbose_name='Validated',
        help_text='Specifies the validation status of the resource',
        default=False,
    )

    validationReport = models.ManyToManyField("documentationInfoType_model",
                                              verbose_name='Validation report',
                                              help_text='A short account of the validation details or a bibliogr' \
                                                        'aphic reference to a document with detailed information on the va' \
                                                        'lidation process and results',
                                              blank=True, null=True,
                                              related_name="validationReport_%(class)s_related", )

    validator = models.ManyToManyField("actorInfoType_model",
                                       verbose_name='Validator',
                                       help_text='Groups information on the person(s) or the organization' \
                                                 '(s) that validated the resource',
                                       blank=True, null=True, related_name="validator_%(class)s_related", )

    back_to_resourceinfotype_model = models.ForeignKey("resourceInfoType_model", blank=True, null=True)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class resourceCreationInfoType_model(SchemaModel):
    """
    Groups information on the creation procedure of a resource
    """

    class Meta:
        verbose_name = "Resource creation"

    __schema_name__ = 'resourceCreationInfoType'
    __schema_fields__ = (
        (u'createdUsingELRCServices', u'createdUsingELRCServices', REQUIRED),
        (u'anonymized', u'anonymized', REQUIRED),
        ('resourceCreator/personInfo', 'resourceCreator', RECOMMENDED),
        ('resourceCreator/organizationInfo', 'resourceCreator', RECOMMENDED),
        (u'fundingProject', u'fundingProject', OPTIONAL),
        (u'creationStartDate', u'creationStartDate', RECOMMENDED),
        (u'creationEndDate', u'creationEndDate', RECOMMENDED),
    )
    __schema_classes__ = {
        u'fundingProject': "projectInfoType_model",
        u'organizationInfo': "organizationInfoType_model",
        u'personInfo': "personInfoType_model",
    }

    createdUsingELRCServices = MetaBooleanField(
        verbose_name='Created using ELRC services',
        help_text='Specifies whether ELRC services have been exploited in ' \
                  'the creation process of the resource; if so, please specify the s' \
                  'ervices used in the description field of the metadata record',
        default=False,
    )

    anonymized = MetaBooleanField(
        verbose_name='Anonymized',
        help_text='Declares whether the resource has been anonymized',
        default=False
    )

    resourceCreator = models.ManyToManyField("actorInfoType_model",
                                             verbose_name='Resource creator',
                                             help_text='Groups information on the person or the organization th' \
                                                       'at has created the resource',
                                             blank=True, null=True, related_name="resourceCreator_%(class)s_related", )

    fundingProject = models.ManyToManyField("projectInfoType_model",
                                            verbose_name='Funding project',
                                            help_text='Groups information on the project that has funded the r' \
                                                      'esource',
                                            blank=True, null=True, related_name="fundingProject_%(class)s_related", )

    creationStartDate = models.DateField(
        verbose_name='Creation start date',
        help_text='The date in which the creation process was started',
        blank=True, null=True, )

    creationEndDate = models.DateField(
        verbose_name='Creation end date',
        help_text='The date in which the creation process was completed',
        blank=True, null=True, )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['resourceCreator', 'fundingProject', 'creationStartDate', 'creationEndDate', ]
        formatstring = u'{} {} {}-{}'
        return self.unicode_(formatstring, formatargs)


CREATIONINFOTYPE_CREATIONMODE_CHOICES = _make_choices_from_list([
    u'automatic', u'manual', u'mixed', u'interactive',
])


# pylint: disable-msg=C0103
class creationInfoType_model(SchemaModel):
    """
    Groups together information on the resource creation (e.g. for
    corpora, selection of texts/audio files/ video files etc. and
    structural encoding thereof; for lexica, construction of lemma
    list etc.)
    """

    class Meta:
        verbose_name = "Creation"

    __schema_name__ = 'creationInfoType'
    __schema_fields__ = (
        (u'originalSource', u'originalSource', RECOMMENDED),
        (u'creationMode', u'creationMode', RECOMMENDED),
        (u'creationModeDetails', u'creationModeDetails', OPTIONAL),
        (u'creationTool', u'creationTool', OPTIONAL),
    )
    __schema_classes__ = {
        u'creationTool': "targetResourceInfoType_model",
        u'originalSource': "targetResourceInfoType_model",
    }

    originalSource = models.ManyToManyField("targetResourceInfoType_model",
                                            verbose_name='Original source',
                                            help_text='The name, the identifier or the url of thethe original ' \
                                                      'resources that were at the base of the creation process of the re' \
                                                      'source',
                                            blank=True, null=True, related_name="originalSource_%(class)s_related", )

    creationMode = models.CharField(
        verbose_name='Creation mode',
        help_text='Specifies whether the resource is created automatically' \
                  ' or in a manual or interactive mode',
        blank=True,
        max_length=30,
        choices=sorted(CREATIONINFOTYPE_CREATIONMODE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    creationModeDetails = XmlCharField(
        verbose_name='Creation mode details',
        help_text='Provides further information on the creation methods an' \
                  'd processes',
        blank=True, max_length=1750, )

    creationTool = models.ManyToManyField("targetResourceInfoType_model",
                                          verbose_name='Creation tool',
                                          help_text='The name, the identifier or the url of the tool used in' \
                                                    ' the creation process',
                                          blank=True, null=True, related_name="creationTool_%(class)s_related", )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class metadataInfoType_model(SchemaModel):
    """
    Groups information on the metadata record itself
    """

    class Meta:
        verbose_name = "Metadata"

    __schema_name__ = 'metadataInfoType'
    __schema_fields__ = (
        (u'metadataCreationDate', u'metadataCreationDate', REQUIRED),
        (u'metadataCreator', u'metadataCreator', OPTIONAL),
        (u'metadataLanguageName', u'metadataLanguageName', OPTIONAL),
        (u'metadataLanguageId', u'metadataLanguageId', OPTIONAL),
        (u'metadataLastDateUpdated', u'metadataLastDateUpdated', OPTIONAL),
    )
    __schema_classes__ = {
        u'metadataCreator': "personInfoType_model",
    }

    metadataCreationDate = models.DateField(
        verbose_name='Metadata creation date',
        help_text='The date of creation of this metadata description (auto' \
                  'matically inserted by the MetaShare software)',
    )

    metadataCreator = models.ManyToManyField("personInfoType_model",
                                             verbose_name='Metadata creator',
                                             help_text='Groups information on the person that has created the m' \
                                                       'etadata record',
                                             blank=True, null=True, related_name="metadataCreator_%(class)s_related", )

    metadataLanguageName = MultiTextField(max_length=100, widget=MultiChoiceWidget(widget_id=2, choices=
    _make_choices_from_list(sorted(iana.get_most_used_languages()))['choices']),
                                          verbose_name='Metadata language',
                                          help_text='The name of the language in which the metadata descript' \
                                                    'ion is written, according to IETF BCP47',
                                          editable=False, blank=True,
                                          validators=[validate_matches_xml_char_production], )

    metadataLanguageId = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=3, max_length=1000),
                                        verbose_name='Metadata language identifier',
                                        help_text='The identifier of the language in which the metadata de' \
                                                  'scription is written according to IETF BCP47',
                                        editable=False, blank=True, validators=[validate_matches_xml_char_production], )

    metadataLastDateUpdated = models.DateField(
        verbose_name='Metadata last date updated',
        help_text='The date of the last updating of the metadata record (a' \
                  'utomatically inserted by the repo software)',
        blank=True, null=True, )

    def save(self, *args, **kwargs):
        """
        Since this field is hidden, language information is drawn from
        the resource description dictionary and are converted to bcp47 valid
        values
        """
        self.metadataLanguageName[:] = []
        self.metadataLanguageId[:] = []
        if 'langs' in kwargs:
            ls = kwargs.pop('langs')
            for i in ls:
                langName = iana.get_language_by_subtag(i)
                self.metadataLanguageName.append(langName)
                self.metadataLanguageId.append(iana.get_language_subtag(langName))
        super(metadataInfoType_model, self).save(*args, **kwargs)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class documentationInfoType_model(SubclassableModel):
    """
    Used to bring together information on documents (as a structured
    bibliographic record or in an unstructured format) and free text
    descriptions
    """

    __schema_name__ = 'SUBCLASSABLE'

    class Meta:
        verbose_name = "Documentation"


DOCUMENTINFOTYPE_DOCUMENTTYPE_CHOICES = _make_choices_from_list([
    u'article', u'book', u'booklet', u'manual', u'techReport',
    u'mastersThesis', u'phdThesis', u'inBook', u'inCollection', u'proceedings',
    u'inProceedings', u'unpublished', u'other',
])


# pylint: disable-msg=C0103
class documentInfoType_model(documentationInfoType_model):
    """
    Groups information on all the documents resporting on various
    aspects of the resource (creation, usage etc.), published or
    unpublished; it is used in various places of the metadata schema
    depending on its role (e.g. usage report, validation report,
    annotation manual etc.)
    """

    class Meta:
        verbose_name = "Document"

    __schema_name__ = 'documentInfoType'
    __schema_fields__ = (
        (u'documentType', u'documentType', REQUIRED),
        (u'title', u'title', REQUIRED),
        (u'author', u'author', OPTIONAL),
        (u'editor', u'editor', OPTIONAL),
        (u'year', u'year', OPTIONAL),
        (u'publisher', u'publisher', OPTIONAL),
        (u'bookTitle', u'bookTitle', OPTIONAL),
        (u'journal', u'journal', OPTIONAL),
        (u'volume', u'volume', OPTIONAL),
        (u'series', u'series', OPTIONAL),
        (u'pages', u'pages', OPTIONAL),
        (u'edition', u'edition', OPTIONAL),
        (u'conference', u'conference', OPTIONAL),
        (u'doi', u'doi', OPTIONAL),
        (u'url', u'url', RECOMMENDED),
        (u'ISSN', u'ISSN', OPTIONAL),
        (u'ISBN', u'ISBN', OPTIONAL),
        (u'keywords', u'keywords', OPTIONAL),
        (u'documentLanguageName', u'documentLanguageName', OPTIONAL),
        (u'documentLanguageId', u'documentLanguageId', OPTIONAL),
    )

    documentType = models.CharField(
        verbose_name='Document type',
        help_text='Specifies the type of the document provided with or rel' \
                  'ated to the resource',

        max_length=30,
        choices=sorted(DOCUMENTINFOTYPE_DOCUMENTTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    title = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                      default_retriever=best_lang_value_retriever,
                      verbose_name='Title',
                      max_val_length=500,
                      help_text='The title of the document reporting on the resource',
                      )

    author = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=4, max_length=1000),
                            verbose_name='Author',
                            help_text='The name(s) of the author(s), in the format described i' \
                                      'n the document',
                            blank=True, validators=[validate_matches_xml_char_production], )

    editor = MultiTextField(max_length=200, widget=MultiFieldWidget(widget_id=5, max_length=200),
                            verbose_name='Editor',
                            help_text='The name of the editor as mentioned in the document',
                            blank=True, validators=[validate_matches_xml_char_production], )

    year = XmlCharField(
        verbose_name='Year (of publication)',
        help_text='The year of publication or, for an unpublished work, th' \
                  'e year it was written',
        blank=True, validators=[validate_xml_schema_year], max_length=1000, )

    publisher = MultiTextField(max_length=200, widget=MultiFieldWidget(widget_id=6, max_length=200),
                               verbose_name='Publisher',
                               help_text='The name of the publisher',
                               blank=True, validators=[validate_matches_xml_char_production], )

    bookTitle = XmlCharField(
        verbose_name='Book title',
        help_text='The title of a book, part of which is being cited',
        blank=True, max_length=200, )

    journal = XmlCharField(
        verbose_name='Journal',
        help_text='A journal name. Abbreviations could also be provided',
        blank=True, max_length=200, )

    volume = XmlCharField(
        verbose_name='Volume',
        help_text='Specifies the volume of a journal or multivolume book',
        blank=True, max_length=1000, )

    series = XmlCharField(
        verbose_name='Series',
        help_text='The name of a series or set of books. When citing an en' \
                  'tire book, the title field gives its title and an optional series' \
                  ' field gives the name of a series or multi-volume set in which th' \
                  'e book is published',
        blank=True, max_length=200, )

    pages = XmlCharField(
        verbose_name='Pages',
        help_text='One or more page numbers or range of page numbers',
        blank=True, max_length=100, )

    edition = XmlCharField(
        verbose_name='Edition',
        help_text='The edition of a book',
        blank=True, max_length=100, )

    conference = XmlCharField(
        verbose_name='Conference',
        help_text='The name of the conference in which the document has be' \
                  'en presented',
        blank=True, max_length=300, )

    doi = XmlCharField(
        verbose_name='DOI',
        help_text='A digital object identifier assigned to the document',
        blank=True, max_length=100, )

    url = XmlCharField(
        verbose_name='URL (Landing page)', validators=[HTTPURI_VALIDATOR],
        help_text='A URL used as homepage of an entity (e.g. of a person, ' \
                  'organization, resource etc.); it provides general information (fo' \
                  'r instance in the case of a resource, it may present a descriptio' \
                  'n of the resource, its creators and possibly include links to the' \
                  ' URL where it can be accessed from)',
        blank=True, max_length=1000, )

    ISSN = XmlCharField(
        verbose_name='ISSN',
        help_text='The International Standard Serial Number used to identi' \
                  'fy a journal',
        blank=True, max_length=100, )

    ISBN = XmlCharField(
        verbose_name='ISBN',
        help_text='The International Standard Book Number',
        blank=True, max_length=100, )

    keywords = MultiTextField(max_length=250, widget=MultiFieldWidget(widget_id=7, max_length=250),
                              verbose_name='Keywords',
                              help_text='The keyword(s) for indexing and classification of the d' \
                                        'ocument',
                              blank=True, validators=[validate_matches_xml_char_production], )

    documentLanguageName = models.CharField(
        verbose_name='Document language',
        help_text='The language the document is written in (according to t' \
                  'he IETF BCP47 guidelines)',
        blank=True, choices=_make_choices_from_list(sorted(iana.get_most_used_languages()))['choices'],
        max_length=150, )

    documentLanguageId = XmlCharField(
        verbose_name='Document language identifier',
        help_text='The id of the language the document is written in (acco' \
                  'rding to the IETF BCP47 guidelines)',
        editable=False, blank=True, max_length=20, )

    source_url = models.URLField(default=DJANGO_URL,
                                 help_text="(Read-only) base URL for the server where the master copy of " \
                                           "the associated entity instance is located.")

    copy_status = models.CharField(default=MASTER, max_length=1, choices=COPY_CHOICES,
                                   help_text="Generalized copy status flag for this entity instance.")

    def save(self, *args, **kwargs):
        """
        Set the adequate documentLanguageId value
        """
        if self.documentLanguageName:
            self.documentLanguageId = iana.get_language_subtag(self.documentLanguageName)

        super(documentInfoType_model, self).save(*args, **kwargs)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['author', 'title', ]
        formatstring = u'{}: {}'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class resourceDocumentationInfoType_model(SchemaModel):
    """
    Groups together information on any document describing the resource
    """

    class Meta:
        verbose_name = "Resource documentation"

    __schema_name__ = 'resourceDocumentationInfoType'
    __schema_fields__ = (
        ('documentation/documentUnstructured', 'documentation', RECOMMENDED),
        ('documentation/documentInfo', 'documentation', RECOMMENDED),
        (u'onLineHelpURL', u'onLineHelpURL', RECOMMENDED),
        (u'samplesLocation', u'samplesLocation', RECOMMENDED),
    )
    __schema_classes__ = {
        u'documentInfo': "documentInfoType_model",
        u'documentUnstructured': "documentUnstructuredString_model",
    }

    documentation = models.ManyToManyField("documentationInfoType_model",
                                           verbose_name='Documentation',
                                           help_text='Refers to papers, manuals, reports etc. describing the ' \
                                                     'resource',
                                           blank=True, null=True, related_name="documentation_%(class)s_related", )

    onLineHelpURL = XmlCharField(
        verbose_name='On line help URL', validators=[HTTPURI_VALIDATOR],
        help_text='URL link to an online manual or help pages',
        blank=True, max_length=1000, )

    samplesLocation = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=8, attrs={'size': '250'}),
                                     verbose_name='Samples location', validators=[HTTPURI_VALIDATOR],
                                     help_text='A url with samples of the resource or, in the case of t' \
                                               'ools, of samples of the output',
                                     blank=True, )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['documentation', ]
        formatstring = u'{}'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class domainInfoType_model(SchemaModel):
    """
    Groups together information on domains represented in the resource;
    can be repeated for parts of the resource with distinct domain
    """

    class Meta:
        verbose_name = "Domain"

    __schema_name__ = 'domainInfoType'
    __schema_fields__ = (
        (u'domain', u'domain', REQUIRED),
        (u'domainId', u'domainId', REQUIRED),
        (u'subdomain', u'subdomain', OPTIONAL),
        (u'subdomainId', u'subdomainId', OPTIONAL),
        (u'conformanceToClassificationScheme', u'conformanceToClassificationScheme', OPTIONAL),
        (u'sizePerDomain', u'sizePerDomain', OPTIONAL),
    )
    __schema_classes__ = {
        u'sizePerDomain': "sizeInfoType_model",
    }

    domain = models.CharField(
        verbose_name='Domain',
        help_text='Specifies the application domain of the resource or the' \
                  ' tool/service according to the EUROVOC thesaurus',

        max_length=100,
        choices=_make_choices_from_list(sorted(eurovoc.get_all_domains()))['choices']
    )

    domainId = models.CharField(
        verbose_name='Domain identifier',
        help_text='The identifier of the application domain of the '
                  'resource or the tool/service, taken from the '
                  'EUROVOC domains: '
                  'http://eurovoc.europa.eu/drupal',
        editable=False,
        max_length=3,
        null=True,
        blank=True
    )

    subdomain = models.CharField(
        max_length=100,
        verbose_name='Subdomain',
        help_text='The name of the application subdomain of the '
                  'resource or the tool/service, taken from the '
                  'EUROVOC domains: http://eurovoc.europa.eu/drupal',
        null=True,
        blank=True,
        choices=_make_choices_from_list \
            (sorted(eurovoc.get_all_subdomains()))['choices'])

    subdomainId = models.CharField(
        verbose_name='Subdomain Identifier',
        help_text='The identifier of the application subdomain of the '
                  'resource or the tool/service, taken from the '
                  'EUROVOC domains: http://eurovoc.europa.eu/drupal',
        editable=False,
        max_length=6,
        null=True,
        blank=True
    )

    conformanceToClassificationScheme = XmlCharField(
        verbose_name='Conformance to classification scheme',
        help_text='Specifies the external classification schemes',
        editable=False,
        max_length=10,
        default="EUROVOC")

    sizePerDomain = models.OneToOneField("sizeInfoType_model",
                                         verbose_name='Size per domain',
                                         help_text='Specifies the size of resource parts per domain',
                                         blank=True, null=True, on_delete=models.SET_NULL, )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    back_to_languagedescriptiontextinfotype_model = models.ForeignKey("languageDescriptionTextInfoType_model",
                                                                      blank=True, null=True)

    back_to_lexicalconceptualresourcetextinfotype_model = models.ForeignKey(
        "lexicalConceptualResourceTextInfoType_model", blank=True, null=True)

    def __unicode__(self):
        if self.subdomainId:
            _unicode = u'Eurovoc {}'.format(self.subdomainId)
        else:
            _unicode = u'Eurovoc {}'.format(self.domainId)
        return _unicode

    def save(self, *args, **kwargs):
        # automatically save the EUROVOC domain id

        if self.domain:
            try:
                self.domainId = eurovoc.get_domain_id(self.domain)
                if self.subdomain:
                    self.subdomainId = eurovoc.get_subdomain_id(''.join(self.subdomain))
                self.conformanceToClassificationScheme = u'EUROVOC'
            except KeyError:
                self.domainId = "N/A"
                # Call save() method from super class with all arguments.

        super(domainInfoType_model, self).save(*args, **kwargs)


ANNOTATIONINFOTYPE_ANNOTATIONTYPE_CHOICES = _make_choices_from_list([
    u'alignment', u'segmentation', u'tokenization', u'segmentationSentence',
    u'segmentationParagraph', u'lemmatization', u'stemming',
    u'structuralAnnotation', u'morphosyntacticAnnotation-bPosTagging',
    u'morphosyntacticAnnotation-posTagging',
    u'syntacticAnnotation-constituencyTrees',
    u'syntacticAnnotation-dependencyTrees',
    u'syntacticAnnotation-subcategorizationFrames',
    u'syntacticosemanticAnnotation-links', u'semanticAnnotation',
    u'semanticAnnotation-certaintyLevel', u'semanticAnnotation-emotions',
    u'semanticAnnotation-entityMentions', u'semanticAnnotation-events',
    u'semanticAnnotation-namedEntities', u'semanticAnnotation-polarity',
    u'semanticAnnotation-semanticClasses',
    u'semanticAnnotation-semanticRelations',
    u'semanticAnnotation-semanticRoles', u'semanticAnnotation-wordSenses',
    u'translation', u'transliteration', u'discourseAnnotation', u'other',
])

ANNOTATIONINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES = _make_choices_from_list([
    u'BML', u'CES', u'EAGLES', u'EML', u'GMX', u'GrAF', u'ISO12620',
    u'ISO16642', u'ISO26162', u'ISO30042', u'ISO704', u'LMF', u'MAF', u'MLIF',
    u'MULTEXT', u'OAXAL', u'OWL', u'pennTreeBank', u'pragueTreebank', u'RDF',
    u'SemAF', u'SemAF_DA', u'SemAF_NE', u'SemAF_SRL', u'SemAF_DS', u'SKOS',
    u'SRX', u'SynAF', u'TBX', u'TMX', u'TEI', u'TEI_P3', u'TEI_P4', u'TEI_P5',
    u'TimeML', u'XCES', u'XLIFF', u'WordNet', u'other',
])

ANNOTATIONINFOTYPE_ANNOTATIONMODE_CHOICES = _make_choices_from_list([
    u'automatic', u'manual', u'mixed', u'interactive',
])

ANNOTATIONINFOTYPE_SEGMENTATIONLEVEL_CHOICES = _make_choices_from_list([
    u'paragraph', u'sentence', u'clause', u'word', u'wordGroup', u'utterance', u'phrase', u'token', u'other',
])


# pylint: disable-msg=C0103
class annotationInfoType_model(SchemaModel):
    """
    Groups information on the annotated part(s) of a resource
    """

    class Meta:
        verbose_name = "Annotation"

    __schema_name__ = 'annotationInfoType'
    __schema_fields__ = (
        (u'annotationType', u'annotationType', REQUIRED),
        (u'annotationStandoff', u'annotationStandoff', OPTIONAL),
        (u'segmentationLevel', u'segmentationLevel', OPTIONAL),
        (u'typesystem', u'typesystem', RECOMMENDED),
        (u'annotationSchema', u'annotationSchema', RECOMMENDED),
        (u'annotationResource', u'annotationResource', RECOMMENDED),
        (u'conformanceToStandardsBestPractices', u'conformanceToStandardsBestPractices', OPTIONAL),
        (u'theoreticModel', u'theoreticModel', OPTIONAL),
        ('annotationManual/documentUnstructured', 'annotationManual', OPTIONAL),
        ('annotationManual/documentInfo', 'annotationManual', OPTIONAL),
        (u'annotationMode', u'annotationMode', RECOMMENDED),
        (u'annotationModeDetails', u'annotationModeDetails', OPTIONAL),
        (u'annotationTool', u'annotationTool', RECOMMENDED),
        (u'sizePerAnnotation', u'sizePerAnnotation', OPTIONAL),
    )
    __schema_classes__ = {
        u'annotationTool': "targetResourceInfoType_model",
        u'documentInfo': "documentInfoType_model",
        u'documentUnstructured': "documentUnstructuredString_model",
        u'sizePerAnnotation': "sizeInfoType_model",
    }

    annotationType = models.CharField(
        verbose_name='Annotation type',
        help_text='Specifies the annotation level of the resource or the a' \
                  'nnotation type a tool/ service requires or produces as an output',

        max_length=150,
        choices=sorted(ANNOTATIONINFOTYPE_ANNOTATIONTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    annotationStandoff = MetaBooleanField(
        verbose_name='Annotation standoff',
        help_text='Indicates whether the annotation is created inline or i' \
                  'n a stand-off fashion',
        blank=True, )

    segmentationLevel = MultiSelectField(
        verbose_name='Segmentation level',
        help_text='Specifies the segmentation unit in terms of which the r' \
                  'esource has been segmented or the level of segmentation a tool/se' \
                  'rvice requires/outputs',
        blank=True,
        max_length=1 + len(ANNOTATIONINFOTYPE_SEGMENTATIONLEVEL_CHOICES['choices']) / 4,
        choices=ANNOTATIONINFOTYPE_SEGMENTATIONLEVEL_CHOICES['choices'],
    )

    typesystem = XmlCharField(
        verbose_name='Typesystem',
        help_text='A name or a url reference to the typesystem used in the' \
                  ' annotation of the resource or used by the tool/service',
        blank=True, max_length=500, )

    annotationSchema = XmlCharField(
        verbose_name='Annotation schema',
        help_text='A name or a url reference to the annotation schema used' \
                  ' in the annotation of the resource or used by the tool/service',
        blank=True, max_length=500, )

    annotationResource = XmlCharField(
        verbose_name='Annotation resource',
        help_text='A name or a url reference to the resource (e.g. tagset,' \
                  ' ontology, term lexicon etc.) used in the annotation of the resou' \
                  'rce or used by the tool/service',
        blank=True, max_length=500, )

    conformanceToStandardsBestPractices = MultiSelectField(
        verbose_name='Conformance to standards / best practices',
        help_text='Specifies the standards or the best practices to which ' \
                  'the tagset used for the annotation conforms',
        blank=True,
        max_length=1 + len(ANNOTATIONINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices']) / 4,
        choices=ANNOTATIONINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices'],
    )

    theoreticModel = XmlCharField(
        verbose_name='Theoretic model',
        help_text='Name of the theoretic model applied for the creation or' \
                  ' enrichment of the resource, and/or a reference (URL or bibliogra' \
                  'phic reference) to informative material about the theoretic model' \
                  ' used',
        blank=True, max_length=500, )

    annotationManual = models.ManyToManyField("documentationInfoType_model",
                                              verbose_name='Annotation manual',
                                              help_text='A bibliographic reference or ms:httpURI link to the ann' \
                                                        'otation manual',
                                              blank=True, null=True,
                                              related_name="annotationManual_%(class)s_related", )

    annotationMode = models.CharField(
        verbose_name='Annotation mode',
        help_text='Indicates whether the resource is annotated manually or' \
                  ' by automatic processes',
        blank=True,
        max_length=100,
        choices=sorted(ANNOTATIONINFOTYPE_ANNOTATIONMODE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    annotationModeDetails = XmlCharField(
        verbose_name='Annotation mode details',
        help_text='Provides further information on annotation process',
        blank=True, max_length=1000, )

    annotationTool = models.ManyToManyField("targetResourceInfoType_model",
                                            verbose_name='Annotation tool',
                                            help_text='The name, the identifier or the url of the tool used fo' \
                                                      'r the annotation of the resource',
                                            blank=True, null=True, related_name="annotationTool_%(class)s_related", )

    sizePerAnnotation = models.OneToOneField("sizeInfoType_model",
                                             verbose_name='Size per annotation',
                                             help_text='Provides information on size for the annotated parts of' \
                                                       ' the resource',
                                             blank=True, null=True, on_delete=models.SET_NULL, )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# Define validator here and not in validators.py to avoid circular import

def validate_target_resource(value):
    if value.isdigit() and not resourceInfoType_model.objects.filter(id=value, storage_object__deleted=False).first():
        raise ValidationError(u'The resource with id {} does not exist'.format(value))


# pylint: disable-msg=C0103
class targetResourceInfoType_model(SchemaModel):
    """
    Groups information on the resource related to the one being
    described; can be an identifier, a resource name or a URL
    """

    class Meta:
        verbose_name = "Target resource"

    __schema_name__ = 'targetResourceInfoType'
    __schema_fields__ = (
        (u'targetResourceNameURI', u'targetResourceNameURI', REQUIRED),
    )

    targetResourceNameURI = XmlCharField(
        verbose_name='Target resource',
        help_text='The full name or a url to a resource related to the one' \
                  ' being described; to be used for identifiers also for this versio' \
                  'n',
        max_length=4500, validators=[validate_target_resource])

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['targetResourceNameURI', ]
        formatstring = u'{}'
        return self.unicode_(formatstring, formatargs)


RELATIONINFOTYPE_RELATIONTYPE_CHOICES = _make_choices_from_list([
    u'isPartOf', u'isPartWith', u'hasPart', u'isVersionOf', u'hasVersion',
    u'isAnnotatedVersionOf', u'hasAnnotatedVersion', u'isAlignedVersionOf',
    u'hasAlignedVersion', u'isRelatedTo', u'isConvertedVersionOf', u'hasConvertedVersion'
])


# pylint: disable-msg=C0103
class relationInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Relation"

    __schema_name__ = 'relationInfoType'
    __schema_fields__ = (
        (u'relationType', u'relationType', REQUIRED),
        (u'relatedResource', u'relatedResource', REQUIRED),
    )
    __schema_classes__ = {
        u'relatedResource': "targetResourceInfoType_model",
    }

    relationType = models.CharField(
        verbose_name='Relation type',
        help_text='Specifies the type of relation not covered by the ones ' \
                  'proposed by META-SHARE',

        max_length=RELATIONINFOTYPE_RELATIONTYPE_CHOICES['max_length'],
        choices=RELATIONINFOTYPE_RELATIONTYPE_CHOICES['choices'],
    )

    relatedResource = models.ForeignKey("targetResourceInfoType_model",
                                        verbose_name='Related resource',
                                        help_text='The full name, the identifier or the url of the related' \
                                                  ' resource',
                                        )

    back_to_resourceinfotype_model = models.ForeignKey("resourceInfoType_model", blank=True, null=True)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class dependenciesInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Dependencies"

    __schema_name__ = 'dependenciesInfoType'
    __schema_fields__ = (
        (u'requiredSoftware', u'requiredSoftware', OPTIONAL),
        (u'requiredLRs', u'requiredLRs', OPTIONAL),
        (u'dependenciesDetails', u'dependenciesDetails', OPTIONAL),
    )
    __schema_classes__ = {
        u'requiredLRs': "targetResourceInfoType_model",
        u'requiredSoftware': "targetResourceInfoType_model",
    }

    requiredSoftware = models.ManyToManyField("targetResourceInfoType_model",
                                              verbose_name='Required software',
                                              help_text='Additional software required for running a tool and/or ' \
                                                        'computational grammar',
                                              blank=True, null=True,
                                              related_name="requiredSoftware_%(class)s_related", )

    requiredLRs = models.ManyToManyField("targetResourceInfoType_model",
                                         verbose_name='Required Language Resources',
                                         help_text='If for running a tool and/or computational grammar, spe' \
                                                   'cific LRs (e.g. a grammar, a list of words etc.) are required',
                                         blank=True, null=True, related_name="requiredLRs_%(class)s_related", )

    dependenciesDetails = XmlCharField(
        verbose_name='Dependencies details',
        help_text='Provides further information on the dependencies',
        blank=True, max_length=500, )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class communicationInfoType_model(SchemaModel):
    """
    Groups information on communication details of a person or an
    organization
    """

    class Meta:
        verbose_name = "Communication"

    __schema_name__ = 'communicationInfoType'
    __schema_fields__ = (
        (u'email', u'email', OPTIONAL),
        (u'url', u'url', OPTIONAL),
        (u'address', u'address', OPTIONAL),
        (u'zipCode', u'zipCode', OPTIONAL),
        (u'city', u'city', OPTIONAL),
        (u'region', u'region', OPTIONAL),
        (u'country', u'country', OPTIONAL),
        (u'countryId', u'countryId', OPTIONAL),
        (u'telephoneNumber', u'telephoneNumber', OPTIONAL),
    )

    email = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=11, max_length=100),
                           verbose_name='Email', validators=[EMAILADDRESS_VALIDATOR],
                           help_text='The email address of a person or an organization', blank=True
                           )

    url = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=12, max_length=150),
                         verbose_name='URL (Landing page)', validators=[HTTPURI_VALIDATOR],
                         help_text='A URL used as homepage of an entity (e.g. of a person, ' \
                                   'organization, resource etc.); it provides general information (fo' \
                                   'r instance in the case of a resource, it may present a descriptio' \
                                   'n of the resource, its creators and possibly include links to the' \
                                   ' URL where it can be accessed from)',
                         blank=True, )

    address = XmlCharField(
        verbose_name='Address',
        help_text='The street and the number of the postal address of a pe' \
                  'rson or organization',
        blank=True, max_length=200, )

    zipCode = XmlCharField(
        verbose_name='Zip code',
        help_text='The zip code of the postal address of a person or organ' \
                  'ization',
        blank=True, max_length=30, )

    city = XmlCharField(
        verbose_name='City',
        help_text='The name of the city, town or village as mentioned in t' \
                  'he postal address of a person or organization',
        blank=True, max_length=50, )

    region = XmlCharField(
        verbose_name='Region',
        help_text='The name of the region, county or department as mention' \
                  'ed in the postal address of a person or organization',
        blank=True, max_length=100, )

    country = models.CharField(
        verbose_name='Country',
        help_text='The name of the country mentioned in the postal address' \
                  ' of a person or organization as defined in the list of values of ' \
                  'ISO 3166',
        blank=True, max_length=100, choices=country_optgroup_choices())

    countryId = XmlCharField(
        verbose_name='Country identifier',
        help_text='The identifier of the country mentioned in the postal a' \
                  'ddress of a person or organization as defined in the list of valu' \
                  'es of ISO 3166',
        editable=False, blank=True, max_length=1000, )

    telephoneNumber = MultiTextField(max_length=30, widget=MultiFieldWidget(widget_id=13, max_length=30),
                                     verbose_name='Telephone number',
                                     help_text='The telephone number of a person or an organization; re' \
                                               'commended format: +_international code_city code_number',
                                     blank=True, validators=[validate_matches_xml_char_production], )

    def save(self, *args, **kwargs):
        if self.country:
            self.countryId = iana.get_region_subtag(self.country)
        # Call save() method from super class with all arguments.
        super(communicationInfoType_model, self).save(*args, **kwargs)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['email', 'telephoneNumber', ]
        formatstring = u'{} {}'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class actorInfoType_model(SubclassableModel):
    """
    Used to bring persons and organizations (in whatever role they may
    have with regard to the resource, e.g., resource creator, IPR
    holder, etc.)
    """

    __schema_name__ = 'SUBCLASSABLE'

    class Meta:
        verbose_name = "Actor"


# pylint: disable-msg=C0103
class organizationInfoType_model(actorInfoType_model):
    """
    Groups information on organizations related to the resource
    """

    class Meta:
        verbose_name = "Organization"

    __schema_name__ = 'organizationInfoType'
    __schema_fields__ = (
        (u'organizationName', u'organizationName', REQUIRED),
        (u'organizationShortName', u'organizationShortName', OPTIONAL),
        (u'departmentName', u'departmentName', OPTIONAL),
        (u'communicationInfo', u'communicationInfo', REQUIRED),
    )
    __schema_classes__ = {
        u'communicationInfo': "communicationInfoType_model",
    }

    organizationName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                                 default_retriever=best_lang_value_retriever,
                                 verbose_name='Organization name',
                                 max_val_length=150,
                                 help_text='The full name of an organization',
                                 )

    organizationShortName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                                      default_retriever=best_lang_value_retriever,
                                      verbose_name='Organization short name',
                                      max_val_length=100,
                                      help_text='The short name (abbreviation, acronym etc.) used for an' \
                                                ' organization',
                                      blank=True)

    departmentName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                               default_retriever=best_lang_value_retriever,
                               verbose_name='Department name',
                               help_text='The name of the department or unit (e.g. specific unive' \
                                         'rsity faculty/department, department/unit of a research organizat' \
                                         'ion or private company etc.)',
                               blank=True)

    communicationInfo = models.OneToOneField("communicationInfoType_model",
                                             verbose_name='Communication',
                                             help_text='Groups information on communication details of a person' \
                                                       ' or an organization',
                                             )

    source_url = models.URLField(default=DJANGO_URL,
                                 help_text="(Read-only) base URL for the server where the master copy of " \
                                           "the associated entity instance is located.")

    copy_status = models.CharField(default=MASTER, max_length=1, choices=COPY_CHOICES,
                                   help_text="Generalized copy status flag for this entity instance.")

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['organizationName', 'departmentName', ]
        formatstring = u'{} \u2013 department: {}'
        return self.unicode_(formatstring, formatargs)


PERSONINFOTYPE_SEX_CHOICES = _make_choices_from_list([
    u'male', u'female', u'unknown',
])


# pylint: disable-msg=C0103
class personInfoType_model(actorInfoType_model):
    """
    Groups information relevant to persons related to the resource; to
    be used mainly for contact persons, resource creators,
    validators, annotators etc. for whom personal data can be
    provided
    """

    class Meta:
        verbose_name = "Person"

    __schema_name__ = 'personInfoType'
    __schema_fields__ = (
        (u'surname', u'surname', REQUIRED),
        (u'givenName', u'givenName', RECOMMENDED),
        (u'sex', u'sex', RECOMMENDED),
        (u'communicationInfo', u'communicationInfo', REQUIRED),
        (u'position', u'position', OPTIONAL),
        (u'affiliation', u'affiliation', OPTIONAL),
    )
    __schema_classes__ = {
        u'affiliation': "organizationInfoType_model",
        u'communicationInfo': "communicationInfoType_model",
    }

    surname = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                        default_retriever=best_lang_value_retriever,
                        verbose_name='Surname',
                        max_val_length=100,
                        help_text='The surname (family name) of a person related to the re' \
                                  'source',
                        )

    givenName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                          default_retriever=best_lang_value_retriever,
                          verbose_name='Given name',
                          max_val_length=100,
                          help_text='The given name (first name) of a person related to the ' \
                                    'resource; initials can also be used',
                          blank=True)

    sex = models.CharField(
        verbose_name='Sex',
        help_text='The gender of a person related to or participating in t' \
                  'he resource',
        blank=True,
        max_length=30,
        choices=sorted(PERSONINFOTYPE_SEX_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    communicationInfo = models.OneToOneField("communicationInfoType_model",
                                             verbose_name='Communication',
                                             help_text='Groups information on communication details of a person' \
                                                       ' or an organization',
                                             )

    position = XmlCharField(
        verbose_name='Position',
        help_text='The position or the title of a person if affiliated to ' \
                  'an organization',
        blank=True, max_length=100, )

    affiliation = models.ManyToManyField("organizationInfoType_model",
                                         verbose_name='Affiliation',
                                         help_text='Groups information on organization to whom the person i' \
                                                   's affiliated',
                                         blank=True, null=True, related_name="affiliation_%(class)s_related", )

    source_url = models.URLField(default=DJANGO_URL,
                                 help_text="(Read-only) base URL for the server where the master copy of " \
                                           "the associated entity instance is located.")

    copy_status = models.CharField(default=MASTER, max_length=1, choices=COPY_CHOICES,
                                   help_text="Generalized copy status flag for this entity instance.")

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['surname', 'givenName', 'communicationInfo/email', 'affiliation', ]
        formatstring = u'{} {} {} {}'
        return self.unicode_(formatstring, formatargs)


DISTRIBUTIONINFOTYPE_AVAILABILITY_CHOICES = _make_choices_from_list([
    u'available', u'underReview',
])

DISTRIBUTIONINFOTYPE_DISTRIBUTIONMEDIUM_CHOICES = _make_choices_from_list([
    u'webExecutable', u'dataDownloadable', u'other',
])


# pylint: disable-msg=C0103
class distributionInfoType_model(SchemaModel):
    """
    Groups information on the distribution of the resource
    """

    class Meta:
        verbose_name = "Distribution"

    __schema_name__ = 'distributionInfoType'
    __schema_fields__ = (
        (u'availability', u'availability', REQUIRED),
        (u'PSI', u'PSI', OPTIONAL),
        (u'allowsUsesBesidesDGT', u'allowsUsesBesidesDGT', REQUIRED),
        (u'licenceInfo', u'licenceInfo', REQUIRED),
        (u'distributionMedium', u'distributionMedium', RECOMMENDED),
        (u'downloadLocation', u'downloadLocation', OPTIONAL),
        (u'executionLocation', u'executionLocation', OPTIONAL),
        (u'attributionText', u'attributionText', OPTIONAL),
        (u'personalDataIncluded', u'personalDataIncluded', REQUIRED),
        (u'personalDataAdditionalInfo', u'personalDataAdditionalInfo', OPTIONAL),
        (u'sensitiveDataIncluded', u'sensitiveDataIncluded', REQUIRED),
        (u'sensitiveDataAdditionalInfo', u'sensitiveDataAdditionalInfo', OPTIONAL),
        (u'fee', u'fee', OPTIONAL),
        ('iprHolder/personInfo', 'iprHolder', OPTIONAL),
        ('iprHolder/organizationInfo', 'iprHolder', OPTIONAL),
    )
    __schema_classes__ = {
        u'licenceInfo': "licenceInfoType_model",
        u'organizationInfo': "organizationInfoType_model",
        u'personInfo': "personInfoType_model",
    }

    availability = models.CharField(
        verbose_name='Availability',
        help_text='Specifies the availability status of the resource; rest' \
                  'rictionsOfUse can be further used to indicate the specific terms ' \
                  'of availability',
        # editable=False,
        max_length=40,
        choices=sorted(DISTRIBUTIONINFOTYPE_AVAILABILITY_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    PSI = MetaBooleanField(
        verbose_name='PSI',
        help_text='Indicates that the resource falls under the Public Sect' \
                  'or Information regulations',
    )

    allowsUsesBesidesDGT = MetaBooleanField(
        verbose_name='Allows uses besides DGT',
        help_text='Whether the resource can be used for purposes other tha' \
                  'n those of the DGT',
        default=False
    )

    licenceInfo = models.ManyToManyField("licenceInfoType_model",
                                         verbose_name='Licences',
                                         help_text='Groups information on licences for the resource; can be' \
                                                   ' repeated to allow for different modes of access and restrictions' \
                                                   ' of use (e.g. free for academic use, on-a-fee basis for commercia' \
                                                   'l use, download of a sample for free use etc.)',
                                         related_name="licenceInfo_%(class)s_related", )

    distributionMedium = MultiSelectField(
        verbose_name='Distribution medium',
        help_text='Specifies the medium (channel) used for delivery or pro' \
                  'viding access to the resource',
        blank=True,
        max_length=1 + len(DISTRIBUTIONINFOTYPE_DISTRIBUTIONMEDIUM_CHOICES['choices']) / 4,
        choices=DISTRIBUTIONINFOTYPE_DISTRIBUTIONMEDIUM_CHOICES['choices'],
    )

    downloadLocation = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=14, attrs={'size': '250'}),
                                      verbose_name='Download location', validators=[HTTPURI_VALIDATOR],
                                      help_text='Any url where the resource can be downloaded from; plea' \
                                                'se, use if the resource is "downloadable" and you have not upload' \
                                                'ed the resource in the repository',
                                      blank=True, )

    executionLocation = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=15, attrs={'size': '250'}),
                                       verbose_name='Execution location', validators=[HTTPURI_VALIDATOR],
                                       help_text=' Any url where the service providing access to a resour' \
                                                 'ce is being executed; please use for resources that are "accessib' \
                                                 'leThroughInterface" or "webExecutable" ',
                                       blank=True, )

    attributionText = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                                default_retriever=best_lang_value_retriever,
                                verbose_name='Attribution text',
                                max_val_length=1000,
                                help_text=' The text that must be quoted for attribution purposes ' \
                                          'when using a resource - for cases where a resource is provided wi' \
                                          'th a request for attribution; you can use a standard text such as' \
                                          ' "Resource X by Resource Creator Y used under licence Z" ',
                                blank=True)

    personalDataIncluded = MetaBooleanField(
        verbose_name='Personal data included',
        help_text='Specifies whether the resource contains or not personal' \
                  ' data; this might mean that special handling of the resource is r' \
                  'equired (e.g. anonymisation)', default=False
    )

    personalDataAdditionalInfo = XmlCharField(
        verbose_name='Personal data additional',
        help_text='If the resource includes personal data, this field can ' \
                  'be used for entering more information, e.g. whether special handl' \
                  'ing of the resource is required (e.g. anonymisation, further requ' \
                  'est for use etc.)',
        blank=True, max_length=1000, )

    sensitiveDataIncluded = MetaBooleanField(
        verbose_name='Sensitive data included',
        help_text='Specifies whether the resource contains or not sensitiv' \
                  'e data; this might mean that special handling of the resource is ' \
                  'required (e.g. anonymisation)', default=False
    )

    sensitiveDataAdditionalInfo = XmlCharField(
        verbose_name='Sensitive data additional',
        help_text='If the resource includes sensitive data, this field can' \
                  ' be used for entering more information, e.g. whether special hand' \
                  'ling of the resource is required (e.g. anonymisation)',
        blank=True, max_length=1000, )

    fee = XmlCharField(
        verbose_name='Fee',
        help_text='Specifies the costs that are required to access the res' \
                  'ource, a fragment of the resource or to use a tool or service',
        blank=True, max_length=100, )

    iprHolder = models.ManyToManyField("actorInfoType_model",
                                       verbose_name='IPR holder',
                                       help_text='Groups information on a person or an organization who h' \
                                                 'olds the full Intellectual Property Rights (Copyright, trademark ' \
                                                 'etc.) that subsist in the resource. The IPR holder could be diffe' \
                                                 'rent from the creator that may have assigned the rights to the IP' \
                                                 'R holder (e.g. an author as a creator assigns her rights to the p' \
                                                 'ublisher who is the IPR holder) and the distributor that holds a ' \
                                                 'specific licence (i.e. a permission) to distribute the work',
                                       blank=True, null=True, related_name="iprHolder_%(class)s_related", )

    back_to_resourceinfotype_model = models.ForeignKey("resourceInfoType_model", blank=True, null=True)

    def real_unicode_(self):
        formatargs = ['availability']
        formatstring = u'{}'
        if self.back_to_resourceinfotype_model:
            formatargs.append('licenceInfo')
            formatstring = u'{} - {}'
        return self.unicode_(formatstring, formatargs)

    def has_personal_data(self):
        return self.personalDataIncluded

    def has_sensitive_data(self):
        return self.sensitiveDataIncluded

    # def check_attribution_text(self):
    #     from templatetags.replace import pretty_camel
    #     if u'attribution' in self.restrictionsOfUse and \
    #             (not self.attributionText or self.attributionText['en'] == ""):
    #         try:
    #             self.attributionText['en'] = "[Resource A] was created for the European Language " \
    #                                          "Resources Coordination Action (ELRC) (http://lr-coordination.eu/) " \
    #                                          "by [Person X], [Institute of X] " \
    #                                          "with primary data copyrighted by [Z] " \
    #                                          "and is licensed under \"{} {}\" ({})." \
    #                 .format(pretty_camel(self.licence),
    #                         LICENCES_DETAILS[self.licence]["version"],
    #                         LICENCES_DETAILS[self.licence]["url"])
    #         except KeyError:
    #             pass

    # def save(self, *args, **kwargs):
    #     licences = []
    #     for licenceInfo in self.licenceInfo.all():
    #         licences.append(licenceInfo.licence)
    #     if u'underReview' in licences:
    #         self.availability = u'underReview'
    #     else:
    #         self.availability = u'available'
    #
    #     # Call save() method from super class with all arguments.
    #     super(distributionInfoType_model, self).save(*args, **kwargs)


LICENCEINFOTYPE_LICENCE_CHOICES = _make_choices_from_list([
    # International/National Data Licences
    u'CC0-1.0',
    u'CC-BY-4.0',
    u'CC-BY-NC-4.0',
    u'CC-BY-NC-ND-4.0',
    u'CC-BY-NC-SA-4.0',
    u'CC-BY-ND-4.0',
    u'CC-BY-SA-4.0',
    u'ODbL-1.0',
    u'ODC-BY-1.0',
    u'OGL-3.0',
    u'PDDL-1.0',
    u'openUnder-PSI',
    u'CC-BY-3.0',
    u'CC-BY-NC-3.0',
    u'CC-BY-NC-ND-3.0',
    u'CC-BY-NC-SA-3.0',
    u'CC-BY-ND-3.0',
    u'CC-BY-SA-3.0',
    u'CC-BY-2.0',
    u'CC-BY-NC-2.0',
    u'CC-BY-NC-ND-2.0',
    u'CC-BY-NC-SA-2.0',
    u'CC-BY-ND-2.0',
    u'CC-BY-SA-2.0',
    # National Data Licences
    u'dl-de/by-2-0',
    u'dl-de/zero-2-0',
    u'IODL-1.0',
    u'LO-OL-v2',
    u'NCGL-1.0',
    u'NLOD-1.0',
    u'CC-BY-SA-2.5_Sl',
    u'CC-BY-2.5-SE',
    # International Software Licences
    u'AGPL-3.0',
    u'Apache-2.0',
    u'BSD-4-Clause',
    u'BSD-3-Clause',
    u'BSD-2-Clause',
    u'EPL-1.0',
    u'GFDL-1.3',
    u'GPL-2.0',
    u'GPL-3.0',
    u'LGPL-3.0',
    u'LGPL-2.1',
    u'MIT',

    u'EUPL-1.0',
    u'EUPL-1.1',
    u'EUPL-1.2',
    # Other
    u'publicDomain',
    u'underReview',
    u'non-standard/Other_Licence/Terms',
])


def licenceinfotype_licence_optgroup_choices():
    """
    Group the choices in groups. The first group is the most used choices
    and the second group is the rest.
    """
    indl = ('International/National Data Licences', LICENCEINFOTYPE_LICENCE_CHOICES['choices'][:24])
    ndl = ('National Data Licences', LICENCEINFOTYPE_LICENCE_CHOICES['choices'][24:32])
    isl = ('International Software Licences', LICENCEINFOTYPE_LICENCE_CHOICES['choices'][32:44])
    isdl = ('International Software & Data Licences', LICENCEINFOTYPE_LICENCE_CHOICES['choices'][44:47])
    other = ('Other', LICENCEINFOTYPE_LICENCE_CHOICES['choices'][47:])
    optgroup = [indl, ndl, isl, isdl, other]
    return optgroup


LICENCES_DETAILS = {
    u'ODC-BY-1.0': {"url": "http://opendatacommons.org/licenses/by/", "version": "1.0"},
    u'ODbL-1.0': {"url": "http://opendatacommons.org/licenses/odbl/", "version": "1.0"},

    u'CC-BY-4.0': {"url": "https://creativecommons.org/licenses/by/4.0/", "version": "4.0"},
    u'CC-BY-NC-4.0': {"url": "https://creativecommons.org/licenses/by-nc/4.0/", "version": "4.0"},
    u'CC-BY-NC-ND-4.0': {"url": "https://creativecommons.org/licenses/by-nc-nd/4.0/", "version": "4.0"},
    u'CC-BY-NC-SA-4.0': {"url": "https://creativecommons.org/licenses/by-nc-sa/4.0/", "version": "4.0"},
    u'CC-BY-ND-4.0': {"url": "https://creativecommons.org/licenses/by-nd/4.0/", "version": "4.0"},
    u'CC-BY-SA-4.0': {"url": "https://creativecommons.org/licenses/by-sa/4.0/", "version": "4.0"},

    u'CC-BY-3.0': {"url": "https://creativecommons.org/licenses/by/3.0/", "version": "3.0"},
    u'CC-BY-NC-3.0': {"url": "https://creativecommons.org/licenses/by-nc/3.0/", "version": "3.0"},
    u'CC-BY-NC-ND-3.0': {"url": "https://creativecommons.org/licenses/by-nc-nd/3.0/", "version": "3.0"},
    u'CC-BY-NC-SA-3.0': {"url": "https://creativecommons.org/licenses/by-nc-sa/3.0/", "version": "3.0"},
    u'CC-BY-ND-3.0': {"url": "https://creativecommons.org/licenses/by-nd/3.0/", "version": "3.0"},
    u'CC-BY-SA-3.0': {"url": "https://creativecommons.org/licenses/by-sa/3.0/", "version": "3.0"},

    u'CC-BY-2.0': {"url": "https://creativecommons.org/licenses/by/2.0/", "version": "2.0"},
    u'CC-BY-NC-2.0': {"url": "https://creativecommons.org/licenses/by-nc/2.0/", "version": "2.0"},
    u'CC-BY-NC-ND-2.0': {"url": "https://creativecommons.org/licenses/by-nc-nd/2.0/", "version": "2.0"},
    u'CC-BY-NC-SA-2.0': {"url": "https://creativecommons.org/licenses/by-nc-sa/2.0/", "version": "2.0"},
    u'CC-BY-ND-2.0': {"url": "https://creativecommons.org/licenses/by-nd/2.0/", "version": "2.0"},
    u'CC-BY-SA-2.0': {"url": "https://creativecommons.org/licenses/by-sa/2.0/", "version": "2.0"},

    u'CC-BY-SA-2.5_Sl': {"url": "https://creativecommons.org/licenses/by-sa/2.5/si/deed.en", "version": "2.5"},
    u'CC-BY-2.5-SE': {"url": "https://creativecommons.org/licenses/by/2.5/se/deed.en", "version": "2.5"},

    u'CC0-1.0': {"url": "https://creativecommons.org/publicdomain/zero/1.0/", "version": "1.0"},
    u'dl-de/by-2-0': {"url": "https://www.govdata.de/dl-de/by-2-0", "version": "2.0"},
    u'dl-de/zero-2-0': {"url": "https://www.govdata.de/dl-de/zero-2-0", "version": "2.0"},
    u'IODL-1.0': {"url": "http://www.formez.it/iodl/", "version": "1.0"},
    u'NLOD-1.0': {"url": "http://data.norge.no/nlod/en/1.0", "version": "1.0"},
    u'OGL-3.0': {"url": "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/", "version": "3.0"},
    u'NCGL-1.0': {
        "url": "http://www.nationalarchives.gov.uk/doc/"
               "non-commercial-government-licence/non-commercial-government-licence.htm",
        "version": "1.0"},
    u'PDDL-1.0': {"url": "http://opendatacommons.org/licenses/pddl/", "version": "1.0"},
    u'AGPL-3.0': {"url": "https://opensource.org/licenses/AGPL-3.0", "version": "3.0"},
    u'Apache-2.0': {"url": "http://www.apache.org/licenses/LICENSE-2.0", "version": "2.0"},
    u'BSD-4-Clause': {"url": "https://directory.fsf.org/wiki/License:BSD_4Clause", "version": ""},
    u'BSD-3-Clause': {"url": "http://www.opensource.org/licenses/BSD-3-Clause", "version": ""},
    u'BSD-2-Clause': {"url": "http://www.opensource.org/licenses/BSD-2-Clause", "version": ""},
    u'GFDL-1.3': {"url": "http://www.gnu.org/licenses/fdl-1.3.txt", "version": "1.3"},
    u'GPL-2.0': {"url": "http://www.gnu.org/licenses/gpl-2.0-standalone.html", "version": "2.0"},
    u'GPL-3.0': {"url": "http://www.gnu.org/licenses/gpl-3.0-standalone.html", "version": "3.0"},
    u'LGPL-2.1': {"url": "http://www.gnu.org/licenses/lgpl-2.1-standalone.html", "version": "2.1"},
    u'LGPL-3.0': {"url": "http://www.gnu.org/licenses/lgpl-3.0-standalone.html", "version": "3.0"},
    u'MIT': {"url": "http://www.opensource.org/licenses/MIT", "version": ""},
    u'EPL-1.0': {"url": "http://www.eclipse.org/legal/epl-v10.html", "version": "1.0"},
    u'EUPL-1.0': {"url": "http://ec.europa.eu/idabc/servlets/Doc027f.pdf?id=31096", "version": "1.0"},
    u'EUPL-1.1': {
        "url": "https://joinup.ec.europa.eu/sites/default/files/custom-page/attachment/eupl1.1.-licence-en_0.pdf",
        "version": "1.1"},
    u'EUPL-1.2': {"url": "https://joinup.ec.europa.eu/sites/default/files/custom-page/attachment/eupl_v1.2_en.pdf",
                  "version": "1.2"},
    u'LO-OL-v2': {"url": "https://wiki.data.gouv.fr/images/9/9d/Licence_Ouverte.pdf", "version": "1.0"},
}

LICENCEINFOTYPE_CONDITIONSOFUSE_CHOICES = _make_choices_from_list([
    u'nonCommercialUse', u'commercialUse', u'attribution', u'shareAlike',
    u'noDerivatives', u'research', u'education', u'compensate', u'other',
])

# TODO: Add MORE
LICENCES_TO_CONDITIONS = {
    u'ODC-BY-1.0': [u'attribution'],
    u'ODbL-1.0': [u'attribution', u'shareAlike'],

    u'CC-BY-4.0': [u'attribution'],
    u'CC-BY-NC-4.0': [u'attribution', u'nonCommercialUse'],
    u'CC-BY-NC-ND-4.0': [u'attribution', u'nonCommercialUse', u'noDerivatives'],
    u'CC-BY-NC-SA-4.0': [u'attribution', u'nonCommercialUse', u'shareAlike'],
    u'CC-BY-ND-4.0': [u'attribution', u'noDerivatives'],
    u'CC-BY-SA-4.0': [u'attribution', u'shareAlike'],

    u'CC-BY-3.0': [u'attribution'],
    u'CC-BY-NC-3.0': [u'attribution', u'nonCommercialUse'],
    u'CC-BY-NC-ND-3.0': [u'attribution', u'nonCommercialUse', u'noDerivatives'],
    u'CC-BY-NC-SA-3.0': [u'attribution', u'nonCommercialUse', u'shareAlike'],
    u'CC-BY-ND-3.0': [u'attribution', u'noDerivatives'],
    u'CC-BY-SA-3.0': [u'attribution', u'shareAlike'],
    u'CC-BY-SA-2.5_Sl': [u'attribution', u'shareAlike'],
    u'CC-BY-2.5-SE': [u'attribution'],

    u'CC-BY-2.0': [u'attribution'],
    u'CC-BY-NC-2.0': [u'attribution', u'nonCommercialUse'],
    u'CC-BY-NC-ND-2.0': [u'attribution', u'nonCommercialUse', u'noDerivatives'],
    u'CC-BY-NC-SA-2.0': [u'attribution', u'nonCommercialUse', u'shareAlike'],
    u'CC-BY-ND-2.0': [u'attribution', u'noDerivatives'],
    u'CC-BY-SA-2.0': [u'attribution', u'shareAlike'],

    u'dl-de/by-2-0': [u'attribution'],
    u'IODL-1.0': [u'attribution'],
    u'NLOD-1.0': [u'attribution'],
    u'OGL-3.0': [u'attribution'],
    u'NCGL-1.0': [u'attribution', u'nonCommercialUse'],
}

LICENCES_NO_CONDITIONS = [
    u'PDDL-1.0', u'CC0-1.0', u'dl-de/zero-2-0'
]


# pylint: disable-msg=C0103
class licenceInfoType_model(SchemaModel):
    """
    Groups information on different forms of distribution of the resource
    and the corresponding licences under which they are distributed;
    can be repeated to allow for different modes of access and conditions
    of use (e.g. free for academic use, on-a-fee basis for commercial use,
    download of a sample for free use etc.)
    """

    class Meta:
        verbose_name = "Licence"

    __schema_name__ = 'licenceInfoType'
    __schema_fields__ = (
        (u'licence', u'licence', REQUIRED),
        (u'otherLicenceName', u'otherLicenceName', OPTIONAL),
        (u'otherLicence_TermsText', u'otherLicence_TermsText', OPTIONAL),
        (u'otherLicence_TermsURL', u'otherLicence_TermsURL', OPTIONAL),
        (u'restrictionsOfUse', u'restrictionsOfUse', OPTIONAL),
    )

    licence = models.CharField(
        verbose_name='Licence',
        help_text='The licence of use for the resource; for an overview of' \
                  ' licences, please visit: https://www.elrc-share.eu/info/#Licensi' \
                  'ng_LRs',

        max_length=100,
        choices=licenceinfotype_licence_optgroup_choices()
    )

    otherLicenceName = XmlCharField(
        verbose_name='Other Licence Name',
        help_text='The name with which a licence is known; to be used for ' \
                  'licences not included in the pre-defined list of recommended lice' \
                  'nces',
        blank=True, null=True, max_length=1500, )

    otherLicence_TermsText = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                                       default_retriever=best_lang_value_retriever,
                                       verbose_name='Other licence terms text',
                                       max_val_length=10000,
                                       help_text='Used for inputting the text of licences that are not in' \
                                                 'cluded in the pre-defined list or terms of use statements associa' \
                                                 'ted with a resource',
                                       blank=True)

    otherLicence_TermsURL = models.URLField(
        verbose_name='Other licence terms URL',
        help_text='Used to provide a hyperlink to a url containing the tex' \
                  't of a licence not included in the predefined list or describing ' \
                  'the terms of use for a language resource',
        blank=True, max_length=1000, )

    restrictionsOfUse = MultiSelectField(
        verbose_name='Conditions of Use',
        help_text='Specifies terms and conditions of use (e.g. attribution' \
                  ', payment etc.) imposed by the licence',
        blank=True,
        max_length=1 + len(LICENCEINFOTYPE_CONDITIONSOFUSE_CHOICES['choices']) / 4,
        choices=LICENCEINFOTYPE_CONDITIONSOFUSE_CHOICES['choices'],
    )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['licence', ]
        formatstring = u'{}'
        return self.unicode_(formatstring, formatargs)

    def save(self, *args, **kwargs):

        if self.licence in LICENCES_TO_CONDITIONS:
            self.restrictionsOfUse = LICENCES_TO_CONDITIONS[self.licence]
        elif self.licence in LICENCES_NO_CONDITIONS:
            self.restrictionsOfUse = None

        # If licence is openUnder-PSI
        if self.licence == u"publicDomain":
            self.otherLicenceName = u"Terms for Public Domain resources"
            self.otherLicence_TermsText["en"] = u"The resource is free of all known legal restrictions."
        elif self.licence == u"openUnder-PSI":
            self.otherLicenceName = u"Terms for PSI-compliant resources"
            self.otherLicence_TermsText["en"] = u"Used for resources that fall under the " \
                                                u"scope of PSI (Public Sector Information) " \
                                                u"regulations, and for which no further information " \
                                                u"is required or available. For more information on the EU " \
                                                u"legislation on the reuse of Public Sector Information, " \
                                                u"see here: https://ec.europa.eu/digital-single-market/en/european-legislation-reuse-public-sector-information."
        # Call save() method from super class with all arguments.
        super(licenceInfoType_model, self).save(*args, **kwargs)


CHARACTERENCODINGINFOTYPE_CHARACTERENCODING_CHOICES = _make_choices_from_list([
    u'UTF-8', u'MacGreek',
    u'US-ASCII', u'Big5', u'Big5-HKSCS', u'Big5_Solaris',
    u'ISO-8859-1', u'ISO-8859-2', u'ISO-8859-3',
    u'ISO-8859-4', u'ISO-8859-5', u'ISO-8859-6',
    u'ISO-8859-7', u'ISO-8859-8', u'ISO-8859-9',
    u'ISO-8859-13', u'ISO-8859-15',
    u'windows-1250', u'windows-1251', u'windows-1252', u'windows-1253',

    u'Cp037', u'Cp1006', u'Cp1025', u'Cp1026', u'Cp1046', u'Cp1047',
    u'Cp1097', u'Cp1098', u'Cp1112', u'Cp1122', u'Cp1123', u'Cp1124',
    u'Cp1140', u'Cp1141', u'Cp1142', u'Cp1143', u'Cp1144', u'Cp1145', u'Cp1146',
    u'Cp1147', u'Cp1148', u'Cp1149', u'Cp1381', u'Cp1383', u'Cp273', u'Cp277',
    u'Cp278', u'Cp280', u'Cp284', u'Cp285', u'Cp297', u'Cp33722', u'Cp420', u'Cp424',
    u'Cp437', u'Cp500', u'Cp737', u'Cp775', u'Cp838', u'Cp850', u'Cp852', u'Cp855',
    u'Cp856', u'Cp857', u'Cp858', u'Cp860', u'Cp861', u'Cp862', u'Cp863', u'Cp864',
    u'Cp865', u'Cp866', u'Cp868', u'Cp869', u'Cp870', u'Cp871', u'Cp874', u'Cp875',
    u'Cp918', u'Cp921', u'Cp922', u'Cp930', u'Cp933', u'Cp935', u'Cp937', u'Cp939',
    u'Cp942', u'Cp942C', u'Cp943', u'Cp943C', u'Cp948', u'Cp949', u'Cp949C',
    u'Cp950', u'Cp964', u'Cp970', u'EUC-JP', u'EUC-KR', u'GB18030', u'GBK',
    u'ISCII91', u'ISO-2022-JP', u'ISO-2022-KR', u'ISO2022_CN_CNS', u'ISO2022_CN_GB', u'JISAutoDetect',
    u'KOI8-R', u'MS874', u'MacArabic', u'MacCentralEurope', u'MacCroatian',
    u'MacCyrillic', u'MacDingbat', u'MacHebrew', u'MacIceland',
    u'MacRoman', u'MacRomania', u'MacSymbol', u'MacThai', u'MacTurkish',
    u'MacUkraine', u'Shift_JIS', u'TIS-620', u'UTF-16',
    u'UTF-16BE', u'UTF-16LE', u'windows-1254', u'windows-1255',
    u'windows-1256', u'windows-1257', u'windows-1258', u'windows-31j',
    u'x-EUC-CN', u'x-EUC-JP-LINUX', u'x-EUC-TW', u'x-MS950-HKSCS',
    u'x-mswin-936', u'x-windows-949', u'x-windows-950'
])


def characterencodinginfotype_characterencoding_optgroup_choices():
    """
    Group the choices in groups. The first group is the most used choices
    and the second group is the rest.
    """
    most_used_choices = ('', CHARACTERENCODINGINFOTYPE_CHARACTERENCODING_CHOICES['choices'][:21])
    more_choices = ('More', CHARACTERENCODINGINFOTYPE_CHARACTERENCODING_CHOICES['choices'][21:])
    optgroup = [most_used_choices, more_choices]
    return optgroup


# pylint: disable-msg=C0103
class characterEncodingInfoType_model(SchemaModel):
    """
    Groups together information on character encoding of the resource
    """

    class Meta:
        verbose_name = "Character encoding"

    __schema_name__ = 'characterEncodingInfoType'
    __schema_fields__ = (
        (u'characterEncoding', u'characterEncoding', REQUIRED),
        (u'sizePerCharacterEncoding', u'sizePerCharacterEncoding', OPTIONAL),
    )
    __schema_classes__ = {
        u'sizePerCharacterEncoding': "sizeInfoType_model",
    }

    characterEncoding = models.CharField(
        verbose_name='Character encoding',
        help_text='The name of the character encoding used in the resource' \
                  ' or accepted by the tool/service',
        max_length=100,
        choices=characterencodinginfotype_characterencoding_optgroup_choices(),
    )

    sizePerCharacterEncoding = models.OneToOneField("sizeInfoType_model",
                                                    verbose_name='Size per character encoding',
                                                    help_text='Provides information on the size of the resource parts ' \
                                                              'with different character encoding',
                                                    blank=True, null=True, on_delete=models.SET_NULL, )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    back_to_languagedescriptiontextinfotype_model = models.ForeignKey("languageDescriptionTextInfoType_model",
                                                                      blank=True, null=True)

    back_to_lexicalconceptualresourcetextinfotype_model = models.ForeignKey(
        "lexicalConceptualResourceTextInfoType_model", blank=True, null=True)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


LINGUALITYINFOTYPE_LINGUALITYTYPE_CHOICES = _make_choices_from_list([
    u'monolingual', u'bilingual', u'multilingual',
])

LINGUALITYINFOTYPE_MULTILINGUALITYTYPE_CHOICES = _make_choices_from_list([
    u'parallel', u'comparable', u'multilingualSingleText', u'other',
])


# pylint: disable-msg=C0103
class lingualityInfoType_model(SchemaModel):
    """
    Groups information on the number of languages of the resource part
    and of the way they are combined to each other
    """

    class Meta:
        verbose_name = "Linguality"

    __schema_name__ = 'lingualityInfoType'
    __schema_fields__ = (
        (u'lingualityType', u'lingualityType', REQUIRED),
        (u'multilingualityType', u'multilingualityType', OPTIONAL),
        (u'multilingualityTypeDetails', u'multilingualityTypeDetails', OPTIONAL),
    )

    lingualityType = models.CharField(
        verbose_name='Linguality type',
        help_text='Indicates whether the resource includes one, two or mor' \
                  'e languages',

        max_length=20,
        choices=sorted(LINGUALITYINFOTYPE_LINGUALITYTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    multilingualityType = models.CharField(
        verbose_name='Multilinguality type',
        help_text='Indicates whether the corpus is parallel, comparable or' \
                  ' mixed',
        blank=True,
        max_length=30,
        choices=sorted(LINGUALITYINFOTYPE_MULTILINGUALITYTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    multilingualityTypeDetails = XmlCharField(
        verbose_name='Multilinguality type details',
        help_text='Provides further information on multilinguality of a re' \
                  'source in free text',
        blank=True, max_length=512, )

    def save(self, *args, **kwargs):
        if self.lingualityType == u'monolingual':
            self.multilingualityType = ""
            self.multilingualityTypeDetails = ""

        # Call save() method from super class with all arguments.
        super(lingualityInfoType_model, self).save(*args, **kwargs)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['lingualityType', ]
        formatstring = u'{}'
        return self.unicode_(formatstring, formatargs)


LANGUAGEVARIETYINFOTYPE_LANGUAGEVARIETYTYPE_CHOICES = _make_choices_from_list([
    u'dialect', u'jargon', u'other',
])


# pylint: disable-msg=C0103
class languageVarietyInfoType_model(SchemaModel):
    """
    Groups information on language varieties occurred in the resource
    (e.g. dialects)
    """

    class Meta:
        verbose_name = "Language variety"

    __schema_name__ = 'languageVarietyInfoType'
    __schema_fields__ = (
        (u'languageVarietyType', u'languageVarietyType', REQUIRED),
        (u'languageVarietyName', u'languageVarietyName', REQUIRED),
        (u'sizePerLanguageVariety', u'sizePerLanguageVariety', OPTIONAL),
    )
    __schema_classes__ = {
        u'sizePerLanguageVariety': "sizeInfoType_model",
    }

    languageVarietyType = models.CharField(
        verbose_name='Language variety type',
        help_text='Specifies the type of the language variety that occurs ' \
                  'in the resource or is supported by a tool/service',

        max_length=20,
        choices=sorted(LANGUAGEVARIETYINFOTYPE_LANGUAGEVARIETYTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    languageVarietyName = XmlCharField(
        verbose_name='Language variety name',
        help_text='The name of the language variety that occurs in the res' \
                  'ource or is supported by a tool/service',
        max_length=100, )

    sizePerLanguageVariety = models.OneToOneField("sizeInfoType_model",
                                                  verbose_name='Size per language variety',
                                                  help_text='Provides information on the size per language variety c' \
                                                            'omponent',
                                                  blank=True, null=True, on_delete=models.SET_NULL, )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['languageVarietyName', 'languageVarietyType', ]
        formatstring = u'{} ({})'
        return self.unicode_(formatstring, formatargs)


def languageinfotype_languagename_optgroup_choices():
    """
    Group the choices in groups. The first group the EU languages
    and the second group contains the rest.
    """
    most_used_choices = ('', _make_choices_from_list(iana.get_most_used_languages())['choices'])
    more_choices = ('More', _make_choices_from_list(sorted(iana.get_rest_of_languages()))['choices'])
    optgroup = [most_used_choices, more_choices]
    return optgroup


# pylint: disable-msg=C0103
class languageInfoType_model(SchemaModel):
    """
    Groups information on the languages represented in the resource
    """

    class Meta:
        verbose_name = "Language"

    __schema_name__ = 'languageInfoType'
    __schema_fields__ = (
        (u'languageId', u'languageId', REQUIRED),
        (u'languageName', u'languageName', REQUIRED),
        (u'languageScript', u'languageScript', OPTIONAL),
        (u'region', u'region', OPTIONAL),
        (u'variant', u'variant', OPTIONAL),
        (u'sizePerLanguage', u'sizePerLanguage', OPTIONAL),
        (u'languageVarietyInfo', u'languageVarietyInfo', OPTIONAL),
    )
    __schema_classes__ = {
        u'languageVarietyInfo': "languageVarietyInfoType_model",
        u'sizePerLanguage': "sizeInfoType_model",
    }

    languageId = XmlCharField(
        verbose_name='Language identifier',
        help_text='The identifier of the language that is included in the ' \
                  'resource or supported by the tool/service, according to the IETF ' \
                  'BCP47 guidelines',
        editable=False, max_length=100, )

    languageName = models.CharField(
        verbose_name='Language name',
        help_text='A human understandable name of the language that is use' \
                  'd in the resource; the name is selected according to the IETF BCP' \
                  '47 specifications',
        choices=languageinfotype_languagename_optgroup_choices(), max_length=100, )

    languageScript = models.CharField(
        verbose_name='Language script',
        help_text='A human understandable name of the script used for the ' \
                  'resource, according to the IETF BCP47 specifications; the element' \
                  ' is optional and should only be used for extraordinary cases (e.g' \
                  '. transcribed text in IPA etc.)',
        blank=True, null=True, choices=_make_choices_from_list(sorted(iana.get_all_scripts()))['choices'],
        max_length=100, )

    region = XmlCharField(
        verbose_name='Region',
        help_text='Name of the region where the language of the resource i' \
                  's spoken (e.g. for English as spoken in the US or the UK etc.)',
        blank=True, null=True, choices=_make_choices_from_list(sorted(iana.get_all_regions()))['choices'],
        max_length=100, )

    variant = MultiTextField(max_length=1000, widget=MultiChoiceWidget(widget_id=16, choices=
    _make_choices_from_list(sorted(iana.get_all_variants()))['choices']),
                             verbose_name='Variants',
                             help_text='Name of the variant of the language of the resource is ' \
                                       'spoken (according to IETF BCP47)',
                             blank=True,
                             null=True,
                             validators=[validate_matches_xml_char_production], )

    sizePerLanguage = models.ManyToManyField("sizeInfoType_model",
                                             verbose_name='Size per language',
                                             help_text='Provides information on the size per language component',
                                             blank=True, null=True, related_name="sizePerLanguage_%(class)s_related", )

    languageVarietyInfo = models.ManyToManyField("languageVarietyInfoType_model",
                                                 verbose_name='Language variety',
                                                 help_text='Groups information on language varieties occurred in th' \
                                                           'e resource (e.g. dialects)',
                                                 blank=True, null=True,
                                                 related_name="languageVarietyInfo_%(class)s_related", )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    back_to_languagedescriptiontextinfotype_model = models.ForeignKey("languageDescriptionTextInfoType_model",
                                                                      blank=True, null=True)

    back_to_lexicalconceptualresourcetextinfotype_model = models.ForeignKey(
        "lexicalConceptualResourceTextInfoType_model", blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.languageName:
            if not self.languageScript:
                self.languageScript = \
                    iana.get_suppressed_script_description(self.languageName)
            self.languageId = \
                iana.make_id(self.languageName, self.languageScript, self.region, self.variant)
        # Call save() method from super class with all arguments.
        super(languageInfoType_model, self).save(*args, **kwargs)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['languageName', 'languageId']
        formatstring = u'{} ({})'.encode('utf-8')
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class languageSetInfoType_model(SchemaModel):
    """
    Groups information on the languages of resources used as input or
    output of tools/services
    """

    class Meta:
        verbose_name = "Language Set"

    __schema_name__ = 'languageSetInfo'
    __schema_fields__ = (
        (u'languageId', u'languageId', REQUIRED),
        (u'languageName', u'languageName', REQUIRED),
        (u'languageScript', u'languageScript', OPTIONAL),
        (u'region', u'region', OPTIONAL),
        (u'variant', u'variant', OPTIONAL),
    )

    languageId = XmlCharField(
        verbose_name='Language identifier',
        help_text='The identifier of the language that is included in the ' \
                  'resource or supported by the tool/service, according to the IETF ' \
                  'BCP47 guidelines',
        editable=False, max_length=100, )

    languageName = XmlCharField(
        verbose_name='Language name',
        help_text='A human understandable name of the language that is use' \
                  'd in the resource; the name is selected according to the IETF BCP' \
                  '47 specifications', choices=languageinfotype_languagename_optgroup_choices(), max_length=100, )

    languageScript = XmlCharField(
        verbose_name='Language script',
        help_text='A human understandable name of the script used for the ' \
                  'resource, according to the IETF BCP47 specifications; the element' \
                  ' is optional and should only be used for extraordinary cases (e.g' \
                  '. transcribed text in IPA etc.)',
        blank=True, choices=_make_choices_from_list(sorted(iana.get_all_scripts()))['choices'], max_length=100, )

    region = XmlCharField(
        verbose_name='Region',
        help_text='Name of the region where the language of the resource i' \
                  's spoken (e.g. for English as spoken in the US or the UK etc.)',
        blank=True, choices=_make_choices_from_list(sorted(iana.get_all_regions()))['choices'], max_length=100, )

    variant = MultiTextField(max_length=1000, widget=MultiChoiceWidget(widget_id=17, choices=
    _make_choices_from_list(sorted(iana.get_all_variants()))['choices']),
                             verbose_name='Variants',
                             help_text='Name of the variant of the language of the resource is ' \
                                       'spoken (according to IETF BCP47)',
                             blank=True, validators=[validate_matches_xml_char_production], )

    back_to_inputinfotype_model = models.ForeignKey("inputInfoType_model", blank=True, null=True)

    back_to_outputinfotype_model = models.ForeignKey("outputInfoType_model", blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.languageName:
            if not self.languageScript:
                self.languageScript = \
                    iana.get_suppressed_script_description(self.languageName)
            self.languageId = \
                iana.make_id(self.languageName, self.languageScript, self.region, self.variant)
        # Call save() method from super class with all arguments.
        super(languageSetInfoType_model, self).save(*args, **kwargs)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['languageName', 'languageId']
        formatstring = u'{} ({})'
        return self.unicode_(formatstring, formatargs)


PROJECTINFOTYPE_FUNDINGTYPE_CHOICES = _make_choices_from_list([
    u'other', u'ownFunds', u'nationalFunds', u'euFunds', u'serviceContract',
])


# pylint: disable-msg=C0103
class projectInfoType_model(SchemaModel):
    """
    Groups information on a project related to the resource(e.g. a
    project the resource has been used in; a funded project that led
    to the resource creation etc.)
    """

    class Meta:
        verbose_name = "Project"

    __schema_name__ = 'projectInfoType'
    __schema_fields__ = (
        (u'projectName', u'projectName', REQUIRED),
        (u'projectShortName', u'projectShortName', OPTIONAL),
        (u'projectID', u'projectID', OPTIONAL),
        (u'url', u'url', OPTIONAL),
        (u'fundingType', u'fundingType', REQUIRED),
        (u'funder', u'funder', RECOMMENDED),
        (u'fundingCountry', u'fundingCountry', RECOMMENDED),
        (u'fundingCountryId', u'fundingCountryId', RECOMMENDED),
        (u'projectStartDate', u'projectStartDate', OPTIONAL),
        (u'projectEndDate', u'projectEndDate', OPTIONAL),
    )

    projectName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                            default_retriever=best_lang_value_retriever,
                            verbose_name='Project name',
                            max_val_length=500,
                            help_text='The full name of a project related to the resource',
                            )

    projectShortName = DictField(validators=[validate_lang_code_keys, validate_dict_values],
                                 default_retriever=best_lang_value_retriever,
                                 verbose_name='Project short name',
                                 max_val_length=500,
                                 help_text='A short name or abbreviation of a project related to th' \
                                           'e resource',
                                 blank=True)

    projectID = XmlCharField(
        verbose_name='Project id',
        help_text='An unambiguous referent to a project related to the res' \
                  'ource',
        blank=True, max_length=100, )

    url = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=18, attrs={'size': '250'}),
                         verbose_name='URL (Landing page)', validators=[HTTPURI_VALIDATOR],
                         help_text='A URL used as homepage of an entity (e.g. of a person, ' \
                                   'organization, resource etc.) and/or where an entity (e.g.LR, docu' \
                                   'ment etc.) is located',
                         blank=True, )

    fundingType = MultiSelectField(
        verbose_name='Funding type',
        help_text='Specifies the type of funding of the project',

        max_length=1 + len(PROJECTINFOTYPE_FUNDINGTYPE_CHOICES['choices']) / 4,
        choices=PROJECTINFOTYPE_FUNDINGTYPE_CHOICES['choices'],
    )

    funder = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=19, max_length=100),
                            verbose_name='Funder',
                            help_text='The full name of the funder of the project',
                            blank=True, validators=[validate_matches_xml_char_production], )

    fundingCountry = MultiTextField(max_length=100,
                                    widget=MultiChoiceWidget(widget_id=20, choices=country_optgroup_choices()),
                                    verbose_name='Funding country',
                                    help_text='The name of the funding country, in case of national fu' \
                                              'nding as mentioned in ISO3166',
                                    blank=True, validators=[validate_matches_xml_char_production], )

    fundingCountryId = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=21, max_length=1000),
                                      verbose_name='Funding country identifier',
                                      help_text='The identifier of the funding country, in case of natio' \
                                                'nal funding as mentioned in ISO3166',
                                      editable=False, blank=True, validators=[validate_matches_xml_char_production], )

    projectStartDate = models.DateField(
        verbose_name='Project start date',
        help_text='The starting date of a project related to the resource',
        blank=True, null=True, )

    projectEndDate = models.DateField(
        verbose_name='Project end date',
        help_text='The end date of a project related to the resource',
        blank=True, null=True, )

    source_url = models.URLField(default=DJANGO_URL,
                                 help_text="(Read-only) base URL for the server where the master copy of " \
                                           "the associated entity instance is located.")

    copy_status = models.CharField(default=MASTER, max_length=1, choices=COPY_CHOICES,
                                   help_text="Generalized copy status flag for this entity instance.")

    def save(self, *args, **kwargs):
        if self.fundingCountry:
            # reset the id list
            self.fundingCountryId = []
            for fc in self.fundingCountry:
                self.fundingCountryId.append(iana.get_region_subtag(fc))
        elif self.fundingCountryId:
            for fci in self.fundingCountryId:
                self.fundingCountry.append(iana.get_language_by_subtag(fci))
        # Call save() method from super class with all arguments.
        super(projectInfoType_model, self).save(*args, **kwargs)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['projectName', 'projectShortName', ]
        formatstring = u'{} ({})'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class corpusTextInfoType_model(SchemaModel):
    """
    Groups together information on the text component of a resource
    """

    class Meta:
        verbose_name = "Corpus text"

    __schema_name__ = 'corpusTextInfoType'
    __schema_fields__ = (
        (u'mediaType', u'mediaType', REQUIRED),
        (u'lingualityInfo', u'lingualityInfo', REQUIRED),
        (u'languageInfo', u'languageinfotype_model_set', REQUIRED),
        (u'sizeInfo', u'sizeinfotype_model_set', REQUIRED),
        (u'textFormatInfo', u'textformatinfotype_model_set', REQUIRED),
        (u'characterEncodingInfo', u'characterencodinginfotype_model_set', RECOMMENDED),
        (u'annotationInfo', u'annotationinfotype_model_set', RECOMMENDED),
        (u'domainInfo', u'domaininfotype_model_set', RECOMMENDED),
        (u'textClassificationInfo', u'textclassificationinfotype_model_set', RECOMMENDED),
        (u'creationInfo', u'creationInfo', RECOMMENDED),
    )
    __schema_classes__ = {
        u'annotationInfo': "annotationInfoType_model",
        u'characterEncodingInfo': "characterEncodingInfoType_model",
        u'creationInfo': "creationInfoType_model",
        u'domainInfo': "domainInfoType_model",
        u'languageInfo': "languageInfoType_model",
        u'lingualityInfo': "lingualityInfoType_model",
        u'sizeInfo': "sizeInfoType_model",
        u'textClassificationInfo': "textClassificationInfoType_model",
        u'textFormatInfo': "textFormatInfoType_model",
    }

    mediaType = XmlCharField(
        verbose_name='Media type',
        help_text='Specifies the media type of the resource and basically ' \
                  'corresponds to the physical medium of the content representation.' \
                  ' Each media type is described through a distinctive set of featur' \
                  'es. A resource may consist of parts attributed to different types' \
                  ' of media. A tool/service may take as input/output more than one ' \
                  'different media types.',
        default="text", editable=False, max_length=1000, )

    lingualityInfo = models.OneToOneField("lingualityInfoType_model",
                                          verbose_name='Linguality',
                                          help_text='Groups information on the number of languages of the re' \
                                                    'source part and of the way they are combined to each other',
                                          null=True, blank=True)

    # OneToMany field: languageInfo

    # OneToMany field: sizeInfo

    # OneToMany field: textFormatInfo

    # OneToMany field: characterEncodingInfo

    # OneToMany field: annotationInfo

    # OneToMany field: domainInfo

    # OneToMany field: textClassificationInfo

    creationInfo = models.OneToOneField("creationInfoType_model",
                                        verbose_name='Creation',
                                        help_text='Groups together information on the resource creation (e' \
                                                  '.g. for corpora, selection of texts/audio files/ video files etc.' \
                                                  ' and structural encoding thereof; for lexica, construction of lem' \
                                                  'ma list etc.)',
                                        blank=True, null=True, on_delete=models.SET_NULL, )

    back_to_corpusmediatypetype_model = models.ForeignKey("corpusMediaTypeType_model", blank=True, null=True)

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['lingualityInfo', 'languageInfo', ]
        formatstring = u'text ({} {})'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class textFormatInfoType_model(SchemaModel):
    """
    Groups information on the text format(s) of a resource
    """

    class Meta:
        verbose_name = "Text format"

    __schema_name__ = 'textFormatInfoType'
    __schema_fields__ = (
        (u'dataFormat', u'dataFormat', REQUIRED),
        (u'sizePerTextFormat', u'sizePerTextFormat', OPTIONAL),
    )
    __schema_classes__ = {
        u'sizePerTextFormat': "sizeInfoType_model",
    }

    dataFormat = models.CharField(
        verbose_name='Data format',
        help_text='The data format (usually corresponding to the mime-type' \
                  ') of the resource which is a formalized specifier for the format ' \
                  'included or a data format (mime-type) that the tool/service accep' \
                  'ts, preferrably in conformance with the values of the IANA (Inter' \
                  'net Assigned Numbers Authority); you can select one of the pre-de' \
                  'fined values or add a value, PREFERABLY FROM THE IANA MEDIA MIMET' \
                  'YPE RECOMMENDED VALUES (http://www.iana.org/assignments/media-typ' \
                  'es/media-types.xhtml)',

        max_length=100,
        choices=sorted(TEXTFORMATINFOTYPE_DATAFORMAT_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    sizePerTextFormat = models.OneToOneField("sizeInfoType_model",
                                             verbose_name='Size per text format',
                                             help_text='Provides information on the size of the resource parts ' \
                                                       'with different format',
                                             blank=True, null=True, on_delete=models.SET_NULL, )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    back_to_languagedescriptiontextinfotype_model = models.ForeignKey("languageDescriptionTextInfoType_model",
                                                                      blank=True, null=True)

    back_to_lexicalconceptualresourcetextinfotype_model = models.ForeignKey(
        "lexicalConceptualResourceTextInfoType_model", blank=True, null=True)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


TEXTCLASSIFICATIONINFOTYPE_TEXTGENRE_CHOICES = _make_choices_from_list([
    u'advertising', u'discussion', u'feature', u'fiction', u'information',
    u'instruction', u'nonFiction', u'official', u'private', u'other',
])

TEXTCLASSIFICATIONINFOTYPE_TEXTTYPE_CHOICES = _make_choices_from_list([
    u'academicTexts', u'administrativeTexts', u'blogTexts', u'chatTexts',
    u'faceToFaceConversationsDiscussions', u'emails', u'encyclopaedicTexts',
    u'interviews', u'journalisticTexts', u'letters', u'literaryTexts',
    u'meetingProceedings', u'reviews', u'scripts', u'subtitles',
    u'technicalTexts', u'telephoneConversations', u'tweets', u'other',
])

TEXTCLASSIFICATIONINFOTYPE_CONFORMANCETOCLASSIFICATIONSCHEME_CHOICES = _make_choices_from_list([
    u'ANC_domainClassification', u'ANC_genreClassification',
    u'BNC_domainClassification', u'BNC_textTypeClassification',
    u'DDC_classification', u'libraryOfCongress_domainClassification',
    u'libraryofCongressSubjectHeadings_classification', u'MeSH_classification',
    u'NLK_classification', u'PAROLE_topicClassification',
    u'PAROLE_genreClassification', u'UDC_classification', u'other',
])


# pylint: disable-msg=C0103
class textClassificationInfoType_model(SchemaModel):
    """
    Groups together information on text type/genre of the resource
    """

    class Meta:
        verbose_name = "Text classification"

    __schema_name__ = 'textClassificationInfoType'
    __schema_fields__ = (
        (u'textGenre', u'textGenre', OPTIONAL),
        (u'textType', u'textType', OPTIONAL),
        (u'conformanceToClassificationScheme', u'conformanceToClassificationScheme', OPTIONAL),
        (u'sizePerTextClassification', u'sizePerTextClassification', OPTIONAL),
    )
    __schema_classes__ = {
        u'sizePerTextClassification': "sizeInfoType_model",
    }

    textGenre = models.CharField(
        verbose_name='Text genre',
        help_text='Genre: The conventionalized discourse or text types of ' \
                  'the content of the resource, based on extra-linguistic and intern' \
                  'al linguistic criteria',
        blank=True,
        max_length=50,
        choices=sorted(TEXTCLASSIFICATIONINFOTYPE_TEXTGENRE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    textType = models.CharField(
        verbose_name='Text type',
        help_text='Specifies the type of the text according to a text type' \
                  ' classification',
        blank=True,
        max_length=50,
        choices=sorted(TEXTCLASSIFICATIONINFOTYPE_TEXTTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    conformanceToClassificationScheme = models.CharField(
        verbose_name='Conformance to classification scheme',
        help_text='Specifies the external classification schemes',
        blank=True,
        max_length=100,
        choices=sorted(TEXTCLASSIFICATIONINFOTYPE_CONFORMANCETOCLASSIFICATIONSCHEME_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    sizePerTextClassification = models.OneToOneField("sizeInfoType_model",
                                                     verbose_name='Size per text classification',
                                                     help_text='Provides information on size of resource parts with dif' \
                                                               'ferent text classification',
                                                     blank=True, null=True, on_delete=models.SET_NULL, )

    back_to_corpustextinfotype_model = models.ForeignKey("corpusTextInfoType_model", blank=True, null=True)

    back_to_languagedescriptiontextinfotype_model = models.ForeignKey("languageDescriptionTextInfoType_model",
                                                                      blank=True, null=True)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


LANGUAGEDESCRIPTIONENCODINGINFOTYPE_ENCODINGLEVEL_CHOICES = _make_choices_from_list([
    u'phonetics', u'phonology', u'semantics', u'morphology', u'syntax',
    u'pragmatics', u'other',
])

LANGUAGEDESCRIPTIONENCODINGINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES = _make_choices_from_list([
    u'BML', u'CES', u'EAGLES', u'EML', u'GMX', u'GrAF', u'ISO12620',
    u'ISO16642', u'ISO26162', u'ISO30042', u'ISO704', u'LMF', u'MAF', u'MLIF',
    u'MULTEXT', u'OAXAL', u'OWL', u'pennTreeBank', u'pragueTreebank', u'RDF',
    u'SemAF', u'SemAF_DA', u'SemAF_NE', u'SemAF_SRL', u'SemAF_DS', u'SKOS',
    u'SRX', u'SynAF', u'TBX', u'TMX', u'TEI', u'TEI_P3', u'TEI_P4', u'TEI_P5',
    u'TimeML', u'XCES', u'XLIFF', u'WordNet', u'other',
])

LANGUAGEDESCRIPTIONENCODINGINFOTYPE_TASK_CHOICES = _make_choices_from_list([
    u'anaphoraResolution', u'chunking', u'parsing', u'npRecognition',
    u'titlesParsing', u'definitionsParsing', u'analysis', u'generation',
    u'other',
])


# pylint: disable-msg=C0103
class languageDescriptionEncodingInfoType_model(SchemaModel):
    """
    Groups together information on the contents of the
    LanguageDescriptions
    """

    class Meta:
        verbose_name = "Language description encoding"

    __schema_name__ = 'languageDescriptionEncodingInfoType'
    __schema_fields__ = (
        (u'encodingLevel', u'encodingLevel', REQUIRED),
        (u'conformanceToStandardsBestPractices', u'conformanceToStandardsBestPractices', RECOMMENDED),
        (u'theoreticModel', u'theoreticModel', RECOMMENDED),
        (u'formalism', u'formalism', OPTIONAL),
        (u'task', u'task', RECOMMENDED),
    )

    encodingLevel = MultiSelectField(
        verbose_name='Encoding level',
        help_text='Information on the linguistic levels covered by the res' \
                  'ource (grammar or lexical/conceptual resource)',

        max_length=1 + len(LANGUAGEDESCRIPTIONENCODINGINFOTYPE_ENCODINGLEVEL_CHOICES['choices']) / 4,
        choices=LANGUAGEDESCRIPTIONENCODINGINFOTYPE_ENCODINGLEVEL_CHOICES['choices'],
    )

    conformanceToStandardsBestPractices = MultiSelectField(
        verbose_name='Conformance to standards / best practices',
        help_text='Specifies the standards or the best practices to which ' \
                  'the tagset used for the annotation conforms',
        blank=True,
        max_length=1 + len(
            LANGUAGEDESCRIPTIONENCODINGINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices']) / 4,
        choices=LANGUAGEDESCRIPTIONENCODINGINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices'],
    )

    theoreticModel = MultiTextField(max_length=500, widget=MultiFieldWidget(widget_id=22, max_length=500),
                                    verbose_name='Theoretic model',
                                    help_text='Name of the theoretic model applied for the creation/en' \
                                              'richment of the resource, and/or reference (URL or bibliographic ' \
                                              'reference) to informative material about the theoretic model used' \
                                              '',
                                    blank=True, validators=[validate_matches_xml_char_production], )

    formalism = XmlCharField(
        verbose_name='Formalism',
        help_text='Reference (name, bibliographic reference or link to url' \
                  ') for the formalism used for the creation/enrichment of the resou' \
                  'rce (grammar or tool/service)',
        blank=True, max_length=1000, )

    task = MultiSelectField(
        verbose_name='Task',
        help_text='An indication of the task performed by the grammar',
        blank=True,
        max_length=1 + len(LANGUAGEDESCRIPTIONENCODINGINFOTYPE_TASK_CHOICES['choices']) / 4,
        choices=LANGUAGEDESCRIPTIONENCODINGINFOTYPE_TASK_CHOICES['choices'],
    )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class languageDescriptionTextInfoType_model(SchemaModel):
    """
    Groups together all information relevant to the text module of a
    language description (e.g. format, languages, size etc.); it is
    obligatory for all language descriptions
    """

    class Meta:
        verbose_name = "Language description text"

    __schema_name__ = 'languageDescriptionTextInfoType'
    __schema_fields__ = (
        (u'mediaType', u'mediaType', REQUIRED),
        (u'lingualityInfo', u'lingualityInfo', REQUIRED),
        (u'languageInfo', u'languageinfotype_model_set', REQUIRED),
        (u'sizeInfo', u'sizeinfotype_model_set', RECOMMENDED),
        (u'textFormatInfo', u'textformatinfotype_model_set', RECOMMENDED),
        (u'characterEncodingInfo', u'characterencodinginfotype_model_set', RECOMMENDED),
        (u'domainInfo', u'domaininfotype_model_set', RECOMMENDED),
        (u'textClassificationInfo', u'textclassificationinfotype_model_set', RECOMMENDED),
    )
    __schema_classes__ = {
        u'characterEncodingInfo': "characterEncodingInfoType_model",
        u'domainInfo': "domainInfoType_model",
        u'languageInfo': "languageInfoType_model",
        u'lingualityInfo': "lingualityInfoType_model",
        u'sizeInfo': "sizeInfoType_model",
        u'textClassificationInfo': "textClassificationInfoType_model",
        u'textFormatInfo': "textFormatInfoType_model",
    }

    mediaType = XmlCharField(
        verbose_name='Media type',
        help_text='Specifies the media type of the resource and basically ' \
                  'corresponds to the physical medium of the content representation.' \
                  ' Each media type is described through a distinctive set of featur' \
                  'es. A resource may consist of parts attributed to different types' \
                  ' of media. A tool/service may take as input/output more than one ' \
                  'different media types.',
        default="text", editable=False, max_length=1000, )

    lingualityInfo = models.OneToOneField("lingualityInfoType_model",
                                          verbose_name='Linguality',
                                          help_text='Groups information on the number of languages of the re' \
                                                    'source part and of the way they are combined to each other',
                                          null=True, blank=True)

    # OneToMany field: languageInfo

    # OneToMany field: sizeInfo

    # OneToMany field: textFormatInfo

    # OneToMany field: characterEncodingInfo

    # OneToMany field: domainInfo

    # OneToMany field: textClassificationInfo

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_ENCODINGLEVEL_CHOICES = _make_choices_from_list([
    u'phonetics', u'phonology', u'semantics', u'morphology', u'syntax',
    u'pragmatics', u'other',
])

LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_LINGUISTICINFORMATION_CHOICES = _make_choices_from_list([
    u'accentuation', u'lemma', u'lemma-MultiWordUnits', u'lemma-Variants',
    u'lemma-Abbreviations', u'lemma-Compounds', u'lemma-CliticForms',
    u'partOfSpeech', u'morpho-Case', u'morpho-Gender', u'morpho-Number',
    u'morpho-Degree', u'morpho-IrregularForms', u'morpho-Mood',
    u'morpho-Tense', u'morpho-Person', u'morpho-Aspect', u'morpho-Voice',
    u'morpho-Auxiliary', u'morpho-Inflection', u'morpho-Reflexivity',
    u'syntax-SubcatFrame', u'semantics-Traits', u'semantics-SemanticClass',
    u'semantics-CrossReferences', u'semantics-Relations',
    u'semantics-Relations-Hyponyms', u'semantics-Relations-Hyperonyms',
    u'semantics-Relations-Synonyms', u'semantics-Relations-Antonyms',
    u'semantics-Relations-Troponyms', u'semantics-Relations-Meronyms',
    u'usage-Frequency', u'usage-Register', u'usage-Collocations',
    u'usage-Examples', u'usage-Notes', u'definition/gloss',
    u'translationEquivalent', u'phonetics-Transcription', u'semantics-Domain',
    u'semantics-EventType', u'semantics-SemanticRoles',
    u'statisticalProperties', u'morpho-Derivation',
    u'semantics-QualiaStructure', u'syntacticoSemanticLinks', u'other',
])

LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES = _make_choices_from_list([
    u'BML', u'CES', u'EAGLES', u'EML', u'GMX', u'GrAF', u'ISO12620',
    u'ISO16642', u'ISO26162', u'ISO30042', u'ISO704', u'LMF', u'MAF', u'MLIF',
    u'MULTEXT', u'OAXAL', u'OWL', u'pennTreeBank', u'pragueTreebank', u'RDF',
    u'SemAF', u'SemAF_DA', u'SemAF_NE', u'SemAF_SRL', u'SemAF_DS', u'SKOS',
    u'SRX', u'SynAF', u'TBX', u'TMX', u'TEI', u'TEI_P3', u'TEI_P4', u'TEI_P5',
    u'TimeML', u'XCES', u'XLIFF', u'WordNet', u'other',
])

LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_EXTRATEXTUALINFORMATION_CHOICES = _make_choices_from_list([
    u'images', u'videos', u'soundRecordings', u'other',
])

LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_EXTRATEXTUALINFORMATIONUNIT_CHOICES = _make_choices_from_list([
    u'word', u'lemma', u'semantics', u'example', u'syntax', u'lexicalUnit',
    u'other',
])


# pylint: disable-msg=C0103
class lexicalConceptualResourceEncodingInfoType_model(SchemaModel):
    """
    Groups all information regarding the contents of lexical/conceptual
    resources
    """

    class Meta:
        verbose_name = "Lexical conceptual resource encoding"

    __schema_name__ = 'lexicalConceptualResourceEncodingInfoType'
    __schema_fields__ = (
        (u'encodingLevel', u'encodingLevel', REQUIRED),
        (u'linguisticInformation', u'linguisticInformation', RECOMMENDED),
        (u'conformanceToStandardsBestPractices', u'conformanceToStandardsBestPractices', RECOMMENDED),
        (u'theoreticModel', u'theoreticModel', OPTIONAL),
        (u'externalRef', u'externalRef', OPTIONAL),
        (u'extratextualInformation', u'extratextualInformation', OPTIONAL),
        (u'extraTextualInformationUnit', u'extraTextualInformationUnit', OPTIONAL),
    )

    encodingLevel = MultiSelectField(
        verbose_name='Encoding level',
        help_text='Information on the contents of the lexicalConceptualRes' \
                  'ource as regards the linguistic level of analysis',

        max_length=1 + len(LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_ENCODINGLEVEL_CHOICES['choices']) / 4,
        choices=LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_ENCODINGLEVEL_CHOICES['choices'],
    )

    linguisticInformation = MultiSelectField(
        verbose_name='Linguistic information',
        help_text='A more detailed account of the linguistic information c' \
                  'ontained in the lexicalConceptualResource',
        blank=True,
        max_length=1 + len(LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_LINGUISTICINFORMATION_CHOICES['choices']) / 4,
        choices=LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_LINGUISTICINFORMATION_CHOICES['choices'],
    )

    conformanceToStandardsBestPractices = MultiSelectField(
        verbose_name='Conformance to standards / best practices',
        help_text='Specifies the standards or the best practices to which ' \
                  'the tagset used for the annotation conforms',
        blank=True,
        max_length=1 + len(
            LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices']) / 4,
        choices=LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices'],
    )

    theoreticModel = MultiTextField(max_length=500, widget=MultiFieldWidget(widget_id=23, max_length=500),
                                    verbose_name='Theoretic model',
                                    help_text='Name of the theoretic model applied for the creation or' \
                                              ' enrichment of the resource, and/or a reference (URL or bibliogra' \
                                              'phic reference) to informative material about the theoretic model' \
                                              ' used',
                                    blank=True, validators=[validate_matches_xml_char_production], )

    externalRef = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=24, max_length=100),
                                 verbose_name='External reference',
                                 help_text='Another resource to which the lexicalConceptualResource' \
                                           ' is linked (e.g. link to a wordnet or ontology)',
                                 blank=True, validators=[validate_matches_xml_char_production], )

    extratextualInformation = MultiSelectField(
        verbose_name='Extratextual information',
        help_text='An indication of the extratextual information contained' \
                  ' in the lexicalConceptualResouce; can be used as an alternative t' \
                  'o audio, image, videos etc. for cases where these are not conside' \
                  'red an important part of the lcr',
        blank=True,
        max_length=1 + len(LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_EXTRATEXTUALINFORMATION_CHOICES['choices']) / 4,
        choices=LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_EXTRATEXTUALINFORMATION_CHOICES['choices'],
    )

    extraTextualInformationUnit = MultiSelectField(
        verbose_name='Extratextual information unit',
        help_text='The unit of the extratextual information contained in t' \
                  'he lexical conceptual resource',
        blank=True,
        max_length=1 + len(
            LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_EXTRATEXTUALINFORMATIONUNIT_CHOICES['choices']) / 4,
        choices=LEXICALCONCEPTUALRESOURCEENCODINGINFOTYPE_EXTRATEXTUALINFORMATIONUNIT_CHOICES['choices'],
    )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class lexicalConceptualResourceTextInfoType_model(SchemaModel):
    """
    Groups information on the textual part of the lexical/conceptual
    resource
    """

    class Meta:
        verbose_name = "Lexical conceptual resource text"

    __schema_name__ = 'lexicalConceptualResourceTextInfoType'
    __schema_fields__ = (
        (u'mediaType', u'mediaType', REQUIRED),
        (u'lingualityInfo', u'lingualityInfo', REQUIRED),
        (u'languageInfo', u'languageinfotype_model_set', REQUIRED),
        (u'sizeInfo', u'sizeinfotype_model_set', REQUIRED),
        (u'textFormatInfo', u'textformatinfotype_model_set', REQUIRED),
        (u'characterEncodingInfo', u'characterencodinginfotype_model_set', RECOMMENDED),
        (u'domainInfo', u'domaininfotype_model_set', RECOMMENDED),
    )
    __schema_classes__ = {
        u'characterEncodingInfo': "characterEncodingInfoType_model",
        u'domainInfo': "domainInfoType_model",
        u'languageInfo': "languageInfoType_model",
        u'lingualityInfo': "lingualityInfoType_model",
        u'sizeInfo': "sizeInfoType_model",
        u'textFormatInfo': "textFormatInfoType_model",
    }

    mediaType = XmlCharField(
        verbose_name='Media type',
        help_text='Specifies the media type of the resource and basically ' \
                  'corresponds to the physical medium of the content representation.' \
                  ' Each media type is described through a distinctive set of featur' \
                  'es. A resource may consist of parts attributed to different types' \
                  ' of media. A tool/service may take as input/output more than one ' \
                  'different media types.',
        default="text", editable=False, max_length=1000, )

    lingualityInfo = models.OneToOneField("lingualityInfoType_model",
                                          verbose_name='Linguality',
                                          help_text='Groups information on the number of languages of the re' \
                                                    'source part and of the way they are combined to each other',
                                          null=True, blank=True)

    # OneToMany field: languageInfo

    # OneToMany field: sizeInfo

    # OneToMany field: textFormatInfo

    # OneToMany field: characterEncodingInfo

    # OneToMany field: domainInfo

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


INPUTINFOTYPE_MEDIATYPE_CHOICES = _make_choices_from_list([
    u'text', u'textNumerical',
])

INPUTINFOTYPE_RESOURCETYPE_CHOICES = _make_choices_from_list([
    u'corpus', u'lexicalConceptualResource', u'languageDescription',
])

INPUTINFOTYPE_DATAFORMAT_CHOICES = _make_choices_from_list([
    u'text/plain', u'application/vnd.xmi+xml', u'application/xml',
    u'application/x-tmx+xml', u'application/x-xces+xml',
    u'application/tei+xml', u'application/rdf+xml', u'application/xhtml+xml',
    u'text/sgml', u'text/html', u'application/x-tex', u'application/rtf',
    u'application/x-latex', u'text/csv', u'text/tab-separated-values',
    u'application/pdf', u'application/x-msaccess', u'application/x-SDL-TM',
    u"application/x-tbx", u'other',
])

INPUTINFOTYPE_CHARACTERENCODING_CHOICES = _make_choices_from_list([
    u'US-ASCII', u'windows-1250', u'windows-1251', u'windows-1252',
    u'windows-1253', u'windows-1254', u'windows-1257', u'ISO-8859-1',
    u'ISO-8859-2', u'ISO-8859-4', u'ISO-8859-5', u'ISO-8859-7', u'ISO-8859-9',
    u'ISO-8859-13', u'ISO-8859-15', u'KOI8-R', u'UTF-8', u'UTF-16',
    u'UTF-16BE', u'UTF-16LE', u'windows-1255', u'windows-1256',
    u'windows-1258', u'ISO-8859-3', u'ISO-8859-6', u'ISO-8859-8',
    u'windows-31j', u'EUC-JP', u'x-EUC-JP-LINUX', u'Shift_JIS', u'ISO-2022-JP',
    u'x-mswin-936', u'GB18030', u'x-EUC-CN', u'GBK', u'ISCII91',
    u'x-windows-949', u'EUC-KR', u'ISO-2022-KR', u'x-windows-950',
    u'x-MS950-HKSCS', u'x-EUC-TW', u'Big5', u'Big5-HKSCS', u'TIS-620',
    u'Big5_Solaris', u'Cp037', u'Cp273', u'Cp277', u'Cp278', u'Cp280',
    u'Cp284', u'Cp285', u'Cp297', u'Cp420', u'Cp424', u'Cp437', u'Cp500',
    u'Cp737', u'Cp775', u'Cp838', u'Cp850', u'Cp852', u'Cp855', u'Cp856',
    u'Cp857', u'Cp858', u'Cp860', u'Cp861', u'Cp862', u'Cp863', u'Cp864',
    u'Cp865', u'Cp866', u'Cp868', u'Cp869', u'Cp870', u'Cp871', u'Cp874',
    u'Cp875', u'Cp918', u'Cp921', u'Cp922', u'Cp930', u'Cp933', u'Cp935',
    u'Cp937', u'Cp939', u'Cp942', u'Cp942C', u'Cp943', u'Cp943C', u'Cp948',
    u'Cp949', u'Cp949C', u'Cp950', u'Cp964', u'Cp970', u'Cp1006', u'Cp1025',
    u'Cp1026', u'Cp1046', u'Cp1047', u'Cp1097', u'Cp1098', u'Cp1112',
    u'Cp1122', u'Cp1123', u'Cp1124', u'Cp1140', u'Cp1141', u'Cp1142',
    u'Cp1143', u'Cp1144', u'Cp1145', u'Cp1146', u'Cp1147', u'Cp1148',
    u'Cp1149', u'Cp1381', u'Cp1383', u'Cp33722', u'ISO2022_CN_CNS',
    u'ISO2022_CN_GB', u'JISAutoDetect', u'MS874', u'MacArabic',
    u'MacCentralEurope', u'MacCroatian', u'MacCyrillic', u'MacDingbat',
    u'MacGreek', u'MacHebrew', u'MacIceland', u'MacRoman', u'MacRomania',
    u'MacSymbol', u'MacThai', u'MacTurkish', u'MacUkraine',
])

INPUTINFOTYPE_ANNOTATIONTYPE_CHOICES = _make_choices_from_list([
    u'alignment', u'segmentation', u'tokenization', u'segmentationSentence',
    u'segmentationParagraph', u'lemmatization', u'stemming',
    u'structuralAnnotation', u'morphosyntacticAnnotation-bPosTagging',
    u'morphosyntacticAnnotation-posTagging',
    u'syntacticAnnotation-constituencyTrees',
    u'syntacticAnnotation-dependencyTrees',
    u'syntacticAnnotation-subcategorizationFrames',
    u'syntacticosemanticAnnotation-links', u'semanticAnnotation',
    u'semanticAnnotation-certaintyLevel', u'semanticAnnotation-emotions',
    u'semanticAnnotation-entityMentions', u'semanticAnnotation-events',
    u'semanticAnnotation-namedEntities', u'semanticAnnotation-polarity',
    u'semanticAnnotation-semanticClasses',
    u'semanticAnnotation-semanticRelations',
    u'semanticAnnotation-semanticRoles', u'semanticAnnotation-wordSenses',
    u'translation', u'transliteration', u'discourseAnnotation', u'other',
])

INPUTINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES = _make_choices_from_list([
    u'BML', u'CES', u'EAGLES', u'EML', u'GMX', u'GrAF', u'ISO12620',
    u'ISO16642', u'ISO26162', u'ISO30042', u'ISO704', u'LMF', u'MAF', u'MLIF',
    u'MULTEXT', u'OAXAL', u'OWL', u'pennTreeBank', u'pragueTreebank', u'RDF',
    u'SemAF', u'SemAF_DA', u'SemAF_NE', u'SemAF_SRL', u'SemAF_DS', u'SKOS',
    u'SRX', u'SynAF', u'TBX', u'TMX', u'TEI', u'TEI_P3', u'TEI_P4', u'TEI_P5',
    u'TimeML', u'XCES', u'XLIFF', u'WordNet', u'other',
])


# pylint: disable-msg=C0103
class inputInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Input"

    __schema_name__ = 'inputInfoType'
    __schema_fields__ = (
        (u'mediaType', u'mediaType', REQUIRED),
        (u'resourceType', u'resourceType', RECOMMENDED),
        (u'dataFormat', u'dataFormat', OPTIONAL),
        (u'languageSetInfo', u'languagesetinfotype_model_set', OPTIONAL),
        (u'languageVarietyName', u'languageVarietyName', OPTIONAL),
        (u'characterEncoding', u'characterEncoding', OPTIONAL),
        (u'domainSetInfo', u'domainSetInfo', OPTIONAL),
        (u'annotationType', u'annotationType', OPTIONAL),
        (u'typesystem', u'typesystem', OPTIONAL),
        (u'annotationSchema', u'annotationSchema', OPTIONAL),
        (u'annotationResource', u'annotationResource', OPTIONAL),
        (u'conformanceToStandardsBestPractices', u'conformanceToStandardsBestPractices', OPTIONAL),
    )
    __schema_classes__ = {
        u'domainSetInfo': "domainSetInfoType_model",
        u'languageSetInfo': "languageSetInfoType_model",
    }

    mediaType = models.CharField(
        verbose_name='Media type',
        help_text='Specifies the media type of the resource and basically ' \
                  'corresponds to the physical medium of the content representation.' \
                  ' Each media type is described through a distinctive set of featur' \
                  'es. A resource may consist of parts attributed to different types' \
                  ' of media. A tool/service may take as input/output more than one ' \
                  'different media types.',
        default="text", editable=False,
        max_length=30,
        choices=sorted(INPUTINFOTYPE_MEDIATYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    resourceType = MultiSelectField(
        verbose_name='Resource type',
        help_text='The type of the resource that a tool or service takes a' \
                  's input or produces as output',
        blank=True,
        max_length=1 + len(INPUTINFOTYPE_RESOURCETYPE_CHOICES['choices']) / 4,
        choices=INPUTINFOTYPE_RESOURCETYPE_CHOICES['choices'],
    )

    dataFormat = MultiSelectField(
        verbose_name='Data format',
        help_text='The data format (usually corresponding to the mime-type' \
                  ') of the resource which is a formalized specifier for the format ' \
                  'included or a data format (mime-type) that the tool/service accep' \
                  'ts, preferrably in conformance with the values of the IANA (Inter' \
                  'net Assigned Numbers Authority); you can select one of the pre-de' \
                  'fined values or add a value, PREFERABLY FROM THE IANA MEDIA MIMET' \
                  'YPE RECOMMENDED VALUES (http://www.iana.org/assignments/media-typ' \
                  'es/media-types.xhtml)',
        blank=True,
        max_length=1 + len(INPUTINFOTYPE_DATAFORMAT_CHOICES['choices']) / 4,
        choices=INPUTINFOTYPE_DATAFORMAT_CHOICES['choices'],
    )

    # OneToMany field: languageSetInfo

    languageVarietyName = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=25, max_length=100),
                                         verbose_name='Language variety name',
                                         help_text='The name of the language variety that occurs in the res' \
                                                   'ource or is supported by a tool/service',
                                         blank=True, validators=[validate_matches_xml_char_production], )

    characterEncoding = MultiSelectField(
        verbose_name='Character encoding',
        help_text='The name of the character encoding used in the resource' \
                  ' or accepted by the tool/service',
        blank=True,
        max_length=1 + len(INPUTINFOTYPE_CHARACTERENCODING_CHOICES['choices']) / 4,
        choices=INPUTINFOTYPE_CHARACTERENCODING_CHOICES['choices'],
    )

    domainSetInfo = models.ManyToManyField("domainSetInfoType_model",
                                           verbose_name='Domain set', blank=True, null=True,
                                           related_name="domainSetInfo_%(class)s_related", )

    annotationType = MultiSelectField(
        verbose_name='Annotation type',
        help_text='Specifies the annotation level of the resource or the a' \
                  'nnotation type a tool/ service requires or produces as an output',
        blank=True,
        max_length=1 + len(INPUTINFOTYPE_ANNOTATIONTYPE_CHOICES['choices']) / 4,
        choices=INPUTINFOTYPE_ANNOTATIONTYPE_CHOICES['choices'],
    )

    typesystem = XmlCharField(
        verbose_name='Typesystem',
        help_text='A name or a url reference to the typesystem used in the' \
                  ' annotation of the resource or used by the tool/service',
        blank=True, max_length=500, )

    annotationSchema = XmlCharField(
        verbose_name='Annotation schema',
        help_text='A name or a url reference to the annotation schema used' \
                  ' in the annotation of the resource or used by the tool/service',
        blank=True, max_length=500, )

    annotationResource = XmlCharField(
        verbose_name='Annotation resource',
        help_text='A name or a url reference to the resource (ontology, ta' \
                  'gset, term lexicon etc.) used in the annotation of the resource o' \
                  'r used by the tool/service',
        blank=True, max_length=500, )

    conformanceToStandardsBestPractices = MultiSelectField(
        verbose_name='Conformance to standards / best practices',
        help_text='Specifies the standards or the best practices to which ' \
                  'the resource used for the annotation conforms',
        blank=True,
        max_length=1 + len(INPUTINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices']) / 4,
        choices=INPUTINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices'],
    )

    def __unicode__(self):
        _unicode = u'{} id="{}"'.format(self.__schema_name__, self.id)
        return _unicode


OUTPUTINFOTYPE_MEDIATYPE_CHOICES = _make_choices_from_list([
    u'text', u'audio', u'video', u'image', u'textNumerical',
])

OUTPUTINFOTYPE_RESOURCETYPE_CHOICES = _make_choices_from_list([
    u'corpus', u'lexicalConceptualResource', u'languageDescription',
])

OUTPUTINFOTYPE_DATAFORMAT_CHOICES = _make_choices_from_list([
    u'text/plain', u'application/vnd.xmi+xml', u'application/xml',
    u'application/x-tmx+xml', u'application/x-xces+xml',
    u'application/tei+xml', u'application/rdf+xml', u'application/xhtml+xml',
    u'text/sgml', u'text/html', u'application/x-tex', u'application/rtf',
    u'application/x-latex', u'text/csv', u'text/tab-separated-values',
    u'application/pdf', u'application/x-msaccess', u'application/x-SDL-TM',
    u"application/x-tbx", u'other',
])

OUTPUTINFOTYPE_CHARACTERENCODING_CHOICES = _make_choices_from_list([
    u'US-ASCII', u'windows-1250', u'windows-1251', u'windows-1252',
    u'windows-1253', u'windows-1254', u'windows-1257', u'ISO-8859-1',
    u'ISO-8859-2', u'ISO-8859-4', u'ISO-8859-5', u'ISO-8859-7', u'ISO-8859-9',
    u'ISO-8859-13', u'ISO-8859-15', u'KOI8-R', u'UTF-8', u'UTF-16',
    u'UTF-16BE', u'UTF-16LE', u'windows-1255', u'windows-1256',
    u'windows-1258', u'ISO-8859-3', u'ISO-8859-6', u'ISO-8859-8',
    u'windows-31j', u'EUC-JP', u'x-EUC-JP-LINUX', u'Shift_JIS', u'ISO-2022-JP',
    u'x-mswin-936', u'GB18030', u'x-EUC-CN', u'GBK', u'ISCII91',
    u'x-windows-949', u'EUC-KR', u'ISO-2022-KR', u'x-windows-950',
    u'x-MS950-HKSCS', u'x-EUC-TW', u'Big5', u'Big5-HKSCS', u'TIS-620',
    u'Big5_Solaris', u'Cp037', u'Cp273', u'Cp277', u'Cp278', u'Cp280',
    u'Cp284', u'Cp285', u'Cp297', u'Cp420', u'Cp424', u'Cp437', u'Cp500',
    u'Cp737', u'Cp775', u'Cp838', u'Cp850', u'Cp852', u'Cp855', u'Cp856',
    u'Cp857', u'Cp858', u'Cp860', u'Cp861', u'Cp862', u'Cp863', u'Cp864',
    u'Cp865', u'Cp866', u'Cp868', u'Cp869', u'Cp870', u'Cp871', u'Cp874',
    u'Cp875', u'Cp918', u'Cp921', u'Cp922', u'Cp930', u'Cp933', u'Cp935',
    u'Cp937', u'Cp939', u'Cp942', u'Cp942C', u'Cp943', u'Cp943C', u'Cp948',
    u'Cp949', u'Cp949C', u'Cp950', u'Cp964', u'Cp970', u'Cp1006', u'Cp1025',
    u'Cp1026', u'Cp1046', u'Cp1047', u'Cp1097', u'Cp1098', u'Cp1112',
    u'Cp1122', u'Cp1123', u'Cp1124', u'Cp1140', u'Cp1141', u'Cp1142',
    u'Cp1143', u'Cp1144', u'Cp1145', u'Cp1146', u'Cp1147', u'Cp1148',
    u'Cp1149', u'Cp1381', u'Cp1383', u'Cp33722', u'ISO2022_CN_CNS',
    u'ISO2022_CN_GB', u'JISAutoDetect', u'MS874', u'MacArabic',
    u'MacCentralEurope', u'MacCroatian', u'MacCyrillic', u'MacDingbat',
    u'MacGreek', u'MacHebrew', u'MacIceland', u'MacRoman', u'MacRomania',
    u'MacSymbol', u'MacThai', u'MacTurkish', u'MacUkraine',
])

OUTPUTINFOTYPE_ANNOTATIONTYPE_CHOICES = _make_choices_from_list([
    u'alignment', u'segmentation', u'tokenization', u'segmentationSentence',
    u'segmentationParagraph', u'lemmatization', u'stemming',
    u'structuralAnnotation', u'morphosyntacticAnnotation-bPosTagging',
    u'morphosyntacticAnnotation-posTagging',
    u'syntacticAnnotation-constituencyTrees',
    u'syntacticAnnotation-dependencyTrees',
    u'syntacticAnnotation-subcategorizationFrames',
    u'syntacticosemanticAnnotation-links', u'semanticAnnotation',
    u'semanticAnnotation-certaintyLevel', u'semanticAnnotation-emotions',
    u'semanticAnnotation-entityMentions', u'semanticAnnotation-events',
    u'semanticAnnotation-namedEntities', u'semanticAnnotation-polarity',
    u'semanticAnnotation-semanticClasses',
    u'semanticAnnotation-semanticRelations',
    u'semanticAnnotation-semanticRoles', u'semanticAnnotation-wordSenses',
    u'translation', u'transliteration', u'discourseAnnotation', u'other',
])

OUTPUTINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES = _make_choices_from_list([
    u'BML', u'CES', u'EAGLES', u'EML', u'GMX', u'GrAF', u'ISO12620',
    u'ISO16642', u'ISO26162', u'ISO30042', u'ISO704', u'LMF', u'MAF', u'MLIF',
    u'MULTEXT', u'OAXAL', u'OWL', u'pennTreeBank', u'pragueTreebank', u'RDF',
    u'SemAF', u'SemAF_DA', u'SemAF_NE', u'SemAF_SRL', u'SemAF_DS', u'SKOS',
    u'SRX', u'SynAF', u'TBX', u'TMX', u'TEI', u'TEI_P3', u'TEI_P4', u'TEI_P5',
    u'TimeML', u'XCES', u'XLIFF', u'WordNet', u'other',
])


# pylint: disable-msg=C0103
class outputInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Output"

    __schema_name__ = 'outputInfoType'
    __schema_fields__ = (
        (u'mediaType', u'mediaType', REQUIRED),
        (u'resourceType', u'resourceType', RECOMMENDED),
        (u'dataFormat', u'dataFormat', RECOMMENDED),
        (u'languageSetInfo', u'languagesetinfotype_model_set', OPTIONAL),
        (u'languageVarietyName', u'languageVarietyName', OPTIONAL),
        (u'characterEncoding', u'characterEncoding', OPTIONAL),
        (u'annotationType', u'annotationType', OPTIONAL),
        (u'typesystem', u'typesystem', OPTIONAL),
        (u'annotationSchema', u'annotationSchema', OPTIONAL),
        (u'annotationResource', u'annotationResource', OPTIONAL),
        (u'conformanceToStandardsBestPractices', u'conformanceToStandardsBestPractices', OPTIONAL),
    )
    __schema_classes__ = {
        u'languageSetInfo': "languageSetInfoType_model",
    }

    mediaType = MultiSelectField(
        verbose_name='Media type',
        help_text='Specifies the media type of the resource and basically ' \
                  'corresponds to the physical medium of the content representation.' \
                  ' Each media type is described through a distinctive set of featur' \
                  'es. A resource may consist of parts attributed to different types' \
                  ' of media. A tool/service may take as input/output more than one ' \
                  'different media types.',

        max_length=1 + len(OUTPUTINFOTYPE_MEDIATYPE_CHOICES['choices']) / 4,
        choices=OUTPUTINFOTYPE_MEDIATYPE_CHOICES['choices'],
    )

    resourceType = MultiSelectField(
        verbose_name='Resource type',
        help_text='The type of the resource that a tool or service takes a' \
                  's input or produces as output',
        blank=True,
        max_length=1 + len(OUTPUTINFOTYPE_RESOURCETYPE_CHOICES['choices']) / 4,
        choices=OUTPUTINFOTYPE_RESOURCETYPE_CHOICES['choices'],
    )

    dataFormat = MultiSelectField(
        verbose_name='Data format',
        help_text='The data format (usually corresponding to the mime-type' \
                  ') of the resource which is a formalized specifier for the format ' \
                  'included or a data format (mime-type) that the tool/service accep' \
                  'ts, preferrably in conformance with the values of the IANA (Inter' \
                  'net Assigned Numbers Authority); you can select one of the pre-de' \
                  'fined values or add a value, PREFERABLY FROM THE IANA MEDIA MIMET' \
                  'YPE RECOMMENDED VALUES (http://www.iana.org/assignments/media-typ' \
                  'es/media-types.xhtml)',
        blank=True,
        max_length=1 + len(OUTPUTINFOTYPE_DATAFORMAT_CHOICES['choices']) / 4,
        choices=OUTPUTINFOTYPE_DATAFORMAT_CHOICES['choices'],
    )

    # OneToMany field: languageSetInfo

    languageVarietyName = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=26, max_length=100),
                                         verbose_name='Language variety name',
                                         help_text='The name of the language variety that occurs in the res' \
                                                   'ource or is supported by a tool/service',
                                         blank=True, validators=[validate_matches_xml_char_production], )

    characterEncoding = MultiSelectField(
        verbose_name='Character encoding',
        help_text='The name of the character encoding used in the resource' \
                  ' or accepted by the tool/service',
        blank=True,
        max_length=1 + len(OUTPUTINFOTYPE_CHARACTERENCODING_CHOICES['choices']) / 4,
        choices=OUTPUTINFOTYPE_CHARACTERENCODING_CHOICES['choices'],
    )

    annotationType = MultiSelectField(
        verbose_name='Annotation type',
        help_text='Specifies the annotation level of the resource or the a' \
                  'nnotation type a tool/ service requires or produces as an output',
        blank=True,
        max_length=1 + len(OUTPUTINFOTYPE_ANNOTATIONTYPE_CHOICES['choices']) / 4,
        choices=OUTPUTINFOTYPE_ANNOTATIONTYPE_CHOICES['choices'],
    )

    typesystem = XmlCharField(
        verbose_name='Typesystem',
        help_text='A name or a url reference to the typesystem used in the' \
                  ' annotation of the resource or used by the tool/service',
        blank=True, max_length=500, )

    annotationSchema = XmlCharField(
        verbose_name='Annotation schema',
        help_text='A name or a url reference to the annotation schema used' \
                  ' in the annotation of the resource or used by the tool/service',
        blank=True, max_length=500, )

    annotationResource = XmlCharField(
        verbose_name='Annotation resource',
        help_text='A name or a url reference to the resource (ontology, ta' \
                  'gset, term lexicon etc.) used in the annotation of the resource o' \
                  'r used by the tool/service',
        blank=True, max_length=500, )

    conformanceToStandardsBestPractices = MultiSelectField(
        verbose_name='Conformance to standards / best practices',
        help_text='Specifies the standards or the best practices to which ' \
                  'the resource used for the annotation conforms',
        blank=True,
        max_length=1 + len(OUTPUTINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices']) / 4,
        choices=OUTPUTINFOTYPE_CONFORMANCETOSTANDARDSBESTPRACTICES_CHOICES['choices'],
    )

    # def save(self, *args, **kwargs):
    #     if self.languageName:
    #         for ln in self.languageName:
    #             self.languageId.append(iana.get_language_subtag(ln))
    #     super(outputInfoType_model, self).save(*args, **kwargs)

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONLEVEL_CHOICES = _make_choices_from_list([
    u'technological', u'usage', u'impact', u'diagnostic',
])

TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONCRITERIA_CHOICES = _make_choices_from_list([
    u'extrinsic', u'intrinsic',
])

TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONMEASURE_CHOICES = _make_choices_from_list([
    u'human', u'automatic',
])


# pylint: disable-msg=C0103
class toolServiceEvaluationInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Tool service evaluation"

    __schema_name__ = 'toolServiceEvaluationInfoType'
    __schema_fields__ = (
        (u'evaluated', u'evaluated', REQUIRED),
        (u'evaluationLevel', u'evaluationLevel', OPTIONAL),
        (u'evaluationCriteria', u'evaluationCriteria', OPTIONAL),
        (u'evaluationMeasure', u'evaluationMeasure', OPTIONAL),
        ('evaluationReport/documentUnstructured', 'evaluationReport', RECOMMENDED),
        ('evaluationReport/documentInfo', 'evaluationReport', RECOMMENDED),
        (u'evaluationTool', u'evaluationTool', RECOMMENDED),
        (u'evaluationDetails', u'evaluationDetails', RECOMMENDED),
        ('evaluator/personInfo', 'evaluator', OPTIONAL),
        ('evaluator/organizationInfo', 'evaluator', OPTIONAL),
    )
    __schema_classes__ = {
        u'documentInfo': "documentInfoType_model",
        u'documentUnstructured': "documentUnstructuredString_model",
        u'evaluationTool': "targetResourceInfoType_model",
        u'organizationInfo': "organizationInfoType_model",
        u'personInfo': "personInfoType_model",
    }

    evaluated = MetaBooleanField(
        verbose_name='Evaluated',
        help_text='Indicates whether the tool or service has been evaluate' \
                  'd',
    )

    evaluationLevel = MultiSelectField(
        verbose_name='Evaluation level',
        help_text='Indicates the evaluation level',
        blank=True,
        max_length=1 + len(TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONLEVEL_CHOICES['choices']) / 4,
        choices=TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONLEVEL_CHOICES['choices'],
    )

    evaluationCriteria = MultiSelectField(
        verbose_name='Evaluation criteria',
        help_text='Defines the criteria of the evaluation of a tool',
        blank=True,
        max_length=1 + len(TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONCRITERIA_CHOICES['choices']) / 4,
        choices=TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONCRITERIA_CHOICES['choices'],
    )

    evaluationMeasure = MultiSelectField(
        verbose_name='Evaluation measure',
        help_text='Defines whether the evaluation measure is human or auto' \
                  'matic',
        blank=True,
        max_length=1 + len(TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONMEASURE_CHOICES['choices']) / 4,
        choices=TOOLSERVICEEVALUATIONINFOTYPE_EVALUATIONMEASURE_CHOICES['choices'],
    )

    evaluationReport = models.ManyToManyField("documentationInfoType_model",
                                              verbose_name='Evaluation report',
                                              help_text='A bibliographical record of or link to a report describ' \
                                                        'ing the evaluation process, tool, method etc. of the tool or serv' \
                                                        'ice',
                                              blank=True, null=True,
                                              related_name="evaluationReport_%(class)s_related", )

    evaluationTool = models.ManyToManyField("targetResourceInfoType_model",
                                            verbose_name='Evaluation tool',
                                            help_text='The name or id or url of the tool used for the evaluati' \
                                                      'on of the tool or service',
                                            blank=True, null=True, related_name="evaluationTool_%(class)s_related", )

    evaluationDetails = XmlCharField(
        verbose_name='Evaluation details',
        help_text='Provides further information on the evaluation process ' \
                  'of a tool or service',
        blank=True, max_length=500, )

    evaluator = models.ManyToManyField("actorInfoType_model",
                                       verbose_name='Evaluator',
                                       help_text='Groups information on person or organization that evalu' \
                                                 'ated the tool or service',
                                       blank=True, null=True, related_name="evaluator_%(class)s_related", )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


TOOLSERVICEOPERATIONINFOTYPE_OPERATINGSYSTEM_CHOICES = _make_choices_from_list([
    u'os-independent', u'windows', u'linux', u'unix', u'mac-OS',
    u'googleChromeOS', u'iOS', u'android', u'other',
])


# pylint: disable-msg=C0103
class toolServiceOperationInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Tool service operation"

    __schema_name__ = 'toolServiceOperationInfoType'
    __schema_fields__ = (
        (u'operatingSystem', u'operatingSystem', OPTIONAL),
        (u'dependenciesInfo', u'dependenciesInfo', RECOMMENDED),
    )
    __schema_classes__ = {
        u'dependenciesInfo': "dependenciesInfoType_model",
    }

    operatingSystem = MultiSelectField(
        verbose_name='Operating system',
        help_text='The operating system on which the tool will be running',
        blank=True,
        max_length=1 + len(TOOLSERVICEOPERATIONINFOTYPE_OPERATINGSYSTEM_CHOICES['choices']) / 4,
        choices=TOOLSERVICEOPERATIONINFOTYPE_OPERATINGSYSTEM_CHOICES['choices'],
    )

    dependenciesInfo = models.OneToOneField("dependenciesInfoType_model",
                                            verbose_name='Dependencies',
                                            help_text='Groups together information on the dependencies (requir' \
                                                      'ements) of a tool or a language description',
                                            blank=True, null=True, on_delete=models.SET_NULL, )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class toolServiceCreationInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Tool service creation"

    __schema_name__ = 'toolServiceCreationInfoType'
    __schema_fields__ = (
        (u'implementationLanguage', u'implementationLanguage', RECOMMENDED),
        (u'formalism', u'formalism', OPTIONAL),
        (u'originalSource', u'originalSource', OPTIONAL),
        (u'creationDetails', u'creationDetails', OPTIONAL),
    )
    __schema_classes__ = {
        u'originalSource': "targetResourceInfoType_model",
    }

    implementationLanguage = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=27, max_length=100),
                                            verbose_name='Implementation language',
                                            help_text='The programming languages needed for allowing user cont' \
                                                      'ributions, or for running the tools, in case no executables are a' \
                                                      'vailable',
                                            blank=True, validators=[validate_matches_xml_char_production], )

    formalism = MultiTextField(max_length=100, widget=MultiFieldWidget(widget_id=28, max_length=100),
                               verbose_name='Formalism',
                               help_text='Reference (name, bibliographic reference or link to url' \
                                         ') for the formalism used for the creation/enrichment of the resou' \
                                         'rce (grammar or tool/service)',
                               blank=True, validators=[validate_matches_xml_char_production], )

    originalSource = models.ManyToManyField("targetResourceInfoType_model",
                                            verbose_name='Original source',
                                            help_text='The name, the identifier or the url of thethe original ' \
                                                      'resources that were at the base of the creation process of the re' \
                                                      'source',
                                            blank=True, null=True, related_name="originalSource_%(class)s_related", )

    creationDetails = XmlCharField(
        verbose_name='Creation details',
        help_text='Provides additional information on the creation of a to' \
                  'ol or service',
        blank=True, max_length=500, )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class resourceComponentTypeType_model(SubclassableModel):
    __schema_name__ = 'SUBCLASSABLE'

    class Meta:
        verbose_name = "Resource component"


LEXICALCONCEPTUALRESOURCEINFOTYPE_LEXICALCONCEPTUALRESOURCETYPE_CHOICES = _make_choices_from_list([
    u'wordList', u'computationalLexicon', u'ontology', u'wordnet',
    u'thesaurus', u'framenet', u'terminologicalResource',
    u'machineReadableDictionary', u'lexicon', u'other',
])


# pylint: disable-msg=C0103
class lexicalConceptualResourceInfoType_model(resourceComponentTypeType_model):
    """
    Groups together information specific to lexical/conceptual resources
    """

    class Meta:
        verbose_name = "Lexical conceptual resource"

    __schema_name__ = 'lexicalConceptualResourceInfoType'
    __schema_fields__ = (
        (u'resourceType', u'resourceType', REQUIRED),
        (u'lexicalConceptualResourceType', u'lexicalConceptualResourceType', REQUIRED),
        (u'lexicalConceptualResourceEncodingInfo', u'lexicalConceptualResourceEncodingInfo', RECOMMENDED),
        (u'lexicalConceptualResourceMediaType', u'lexicalConceptualResourceMediaType', REQUIRED),
    )
    __schema_classes__ = {
        u'lexicalConceptualResourceEncodingInfo': "lexicalConceptualResourceEncodingInfoType_model",
        u'lexicalConceptualResourceMediaType': "lexicalConceptualResourceMediaTypeType_model",
    }

    resourceType = XmlCharField(
        verbose_name='Resource type',
        help_text='Specifies the type of the resource being described',
        default="lexicalConceptualResource", editable=False, max_length=1000, )

    lexicalConceptualResourceType = models.CharField(
        verbose_name='Lexical conceptual resource type',
        help_text='Specifies the subtype of lexicalConceptualResource',

        max_length=LEXICALCONCEPTUALRESOURCEINFOTYPE_LEXICALCONCEPTUALRESOURCETYPE_CHOICES['max_length'],
        choices=LEXICALCONCEPTUALRESOURCEINFOTYPE_LEXICALCONCEPTUALRESOURCETYPE_CHOICES['choices'],
    )

    lexicalConceptualResourceEncodingInfo = models.OneToOneField("lexicalConceptualResourceEncodingInfoType_model",
                                                                 verbose_name='Lexical / Conceptual resource encoding',
                                                                 help_text='Groups all information regarding the contents of lexica' \
                                                                           'l/conceptual resources',
                                                                 blank=True, null=True, on_delete=models.SET_NULL, )

    lexicalConceptualResourceMediaType = models.OneToOneField("lexicalConceptualResourceMediaTypeType_model",
                                                              verbose_name='Media type component of lexical / conceptual resource',
                                                              help_text='Restriction of mediaType for lexicalConceptualResources' \
                                                                        '',
                                                              )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['lexicalConceptualResourceType', ]
        formatstring = u'lexicalConceptualResource ({})'
        return self.unicode_(formatstring, formatargs)


LANGUAGEDESCRIPTIONINFOTYPE_LANGUAGEDESCRIPTIONTYPE_CHOICES = _make_choices_from_list([
    u'grammar', u'languageModel', u'other',
])


# pylint: disable-msg=C0103
class languageDescriptionInfoType_model(resourceComponentTypeType_model):
    """
    Groups together information on language descriptions (grammars)
    """

    class Meta:
        verbose_name = "Language description"

    __schema_name__ = 'languageDescriptionInfoType'
    __schema_fields__ = (
        (u'resourceType', u'resourceType', REQUIRED),
        (u'languageDescriptionType', u'languageDescriptionType', REQUIRED),
        (u'languageDescriptionEncodingInfo', u'languageDescriptionEncodingInfo', RECOMMENDED),
        (u'languageDescriptionMediaType', u'languageDescriptionMediaType', REQUIRED),
    )
    __schema_classes__ = {
        u'languageDescriptionEncodingInfo': "languageDescriptionEncodingInfoType_model",
        u'languageDescriptionMediaType': "languageDescriptionMediaTypeType_model",
    }

    resourceType = XmlCharField(
        verbose_name='Resource type',
        help_text='Specifies the type of the resource being described',
        default="languageDescription", editable=False, max_length=30, )

    languageDescriptionType = models.CharField(
        verbose_name='Language description type',
        help_text='The type of the language description',
        max_length=30,
        choices=sorted(LANGUAGEDESCRIPTIONINFOTYPE_LANGUAGEDESCRIPTIONTYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    languageDescriptionEncodingInfo = models.OneToOneField("languageDescriptionEncodingInfoType_model",
                                                           verbose_name='Language description encoding',
                                                           help_text='Groups together information on the contents of the Lang' \
                                                                     'uageDescriptions',
                                                           blank=True, null=True, on_delete=models.SET_NULL, )

    languageDescriptionMediaType = models.OneToOneField("languageDescriptionMediaTypeType_model",
                                                        verbose_name='Media type component of language description',
                                                        help_text='Groups information on the media type-specific component' \
                                                                  's for language descriptions',
                                                        )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['languageDescriptionType', ]
        formatstring = u'languageDescription ({})'
        return self.unicode_(formatstring, formatargs)


TOOLSERVICEINFOTYPE_TOOLSERVICETYPE_CHOICES = _make_choices_from_list([
    u'tool', u'service', u'suiteOfTools', u'other',
])

TOOLSERVICEINFOTYPE_FUNCTION_CHOICES = _make_choices_from_list([
    u'alignment', u'phraseAlignment', u'sentenceAlignment', u'wordAlignment',
    u'webCrawling', u'languageIdentification', u'termExtraction',
    u'lexiconAcquisitionFromCorpora', u'lexiconExtractionFromLexica',
    u'bilingualLexiconInduction', u'spellChecking', u'languageModelling',
    u'trainingOfLanguageModels', u'annotation',
    u'annotationOfDocumentStructure', u'structuralAnnotation',
    u'sentenceSplitting', u'paragraphSplitting', u'tokenization',
    u'lemmatization', u'stemming', u'poSTagging', u'belowPoSTagging',
    u'wordSegmentation', u'annotationOfCompounds',
    u'annotationOfDerivationalFeatures', u'chunking', u'parsing',
    u'constituencyParsing', u'dependencyConversion', u'dependencyParsing',
    u'namedEntityRecognition', u'semanticAnnotation',
    u'semanticClassLabelling', u'semanticRelationLabelling',
    u'semanticRoleLabelling', u'frameSemanticParsing',
    u'coReferenceAnnotation', u'formatConversion', u'evaluation',
    u'textCategorization', u'topicDetection', u'validation', u'corpusViewing',
    u'other',
])


# pylint: disable-msg=C0103
class toolServiceInfoType_model(resourceComponentTypeType_model):
    class Meta:
        verbose_name = "Tool service"

    __schema_name__ = 'toolServiceInfoType'
    __schema_fields__ = (
        (u'resourceType', u'resourceType', REQUIRED),
        (u'toolServiceType', u'toolServiceType', REQUIRED),
        (u'function', u'function', REQUIRED),
        (u'languageDependent', u'languageDependent', REQUIRED),
        (u'inputInfo', u'inputInfo', RECOMMENDED),
        (u'outputInfo', u'outputInfo', RECOMMENDED),
        (u'toolServiceOperationInfo', u'toolServiceOperationInfo', RECOMMENDED),
        (u'toolServiceEvaluationInfo', u'toolServiceEvaluationInfo', RECOMMENDED),
        (u'toolServiceCreationInfo', u'toolServiceCreationInfo', OPTIONAL),
    )
    __schema_classes__ = {
        u'inputInfo': "inputInfoType_model",
        u'outputInfo': "outputInfoType_model",
        u'toolServiceCreationInfo': "toolServiceCreationInfoType_model",
        u'toolServiceEvaluationInfo': "toolServiceEvaluationInfoType_model",
        u'toolServiceOperationInfo': "toolServiceOperationInfoType_model",
    }

    resourceType = XmlCharField(
        verbose_name='Resource type',
        help_text='The type of the resource that a tool or service takes a' \
                  's input or produces as output',
        default="toolService", editable=False, max_length=1000, )

    toolServiceType = models.CharField(
        verbose_name='Tool / Service type',
        help_text='Specifies the type of the tool or service',

        max_length=100,
        choices=sorted(TOOLSERVICEINFOTYPE_TOOLSERVICETYPE_CHOICES['choices'],
                       key=lambda choice: choice[1].lower()),
    )

    function = MultiSelectField(
        verbose_name='Function',
        help_text='Specifies the function/operation/task that a tool or we' \
                  'b service performs',

        max_length=1 + len(TOOLSERVICEINFOTYPE_FUNCTION_CHOICES['choices']) / 4,
        choices=TOOLSERVICEINFOTYPE_FUNCTION_CHOICES['choices'],
    )

    languageDependent = MetaBooleanField(
        verbose_name='Language dependent',
        help_text='Indicates whether the operation of the tool or service ' \
                  'is language dependent or not',
    )

    inputInfo = models.OneToOneField("inputInfoType_model",
                                     verbose_name='Input',
                                     help_text='Groups together information on the requirements set on ' \
                                               'the input resource of a tool or service',
                                     blank=True, null=True, on_delete=models.SET_NULL, )

    outputInfo = models.OneToOneField("outputInfoType_model",
                                      verbose_name='Output',
                                      help_text='Groups together information on the requirements set on ' \
                                                'the output of a tool or service',
                                      blank=True, null=True, on_delete=models.SET_NULL, )

    toolServiceOperationInfo = models.OneToOneField("toolServiceOperationInfoType_model",
                                                    verbose_name='Tool / Service operation',
                                                    help_text='Groups together information on the operation of a tool ' \
                                                              'or service',
                                                    blank=True, null=True, on_delete=models.SET_NULL, )

    toolServiceEvaluationInfo = models.OneToOneField("toolServiceEvaluationInfoType_model",
                                                     verbose_name='Tool / Service evaluation',
                                                     help_text='Groups together information on the evaluation status of' \
                                                               ' a tool or service',
                                                     blank=True, null=True, on_delete=models.SET_NULL, )

    toolServiceCreationInfo = models.OneToOneField("toolServiceCreationInfoType_model",
                                                   verbose_name='Tool / Service creation',
                                                   help_text='Groups together information on the creation of a tool o' \
                                                             'r service',
                                                   blank=True, null=True, on_delete=models.SET_NULL, )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['toolServiceType', ]
        formatstring = u'toolService ({})'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class corpusInfoType_model(resourceComponentTypeType_model):
    """
    Groups together information on corpora of all media types
    """

    class Meta:
        verbose_name = "Corpus"

    __schema_name__ = 'corpusInfoType'
    __schema_fields__ = (
        (u'resourceType', u'resourceType', REQUIRED),
        (u'corpusMediaType', u'corpusMediaType', REQUIRED),
    )
    __schema_classes__ = {
        u'corpusMediaType': "corpusMediaTypeType_model",
    }

    resourceType = XmlCharField(
        verbose_name='Resource type',
        help_text='Specifies the type of the resource being described',
        default="corpus", editable=False, max_length=1000, )

    corpusMediaType = models.OneToOneField("corpusMediaTypeType_model",
                                           verbose_name='Media type component of corpus',
                                           help_text='Used to specify the media type specific to corpora and ' \
                                                     'group together the relevant information',
                                           )

    def real_unicode_(self):
        # pylint: disable-msg=C0301
        formatargs = ['corpusMediaType/corpusTextInfo', ]
        formatstring = u'corpus ({})'
        return self.unicode_(formatstring, formatargs)


# pylint: disable-msg=C0103
class corpusMediaTypeType_model(SchemaModel):
    class Meta:
        verbose_name = "Media type component of corpus"

    __schema_name__ = 'corpusMediaTypeType'
    __schema_fields__ = (
        (u'corpusTextInfo', u'corpustextinfotype_model_set', REQUIRED),
    )
    __schema_classes__ = {
        u'corpusTextInfo': "corpusTextInfoType_model",
    }

    # OneToMany field: corpusTextInfo

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class languageDescriptionMediaTypeType_model(SchemaModel):
    class Meta:
        verbose_name = "Language description media"

    __schema_name__ = 'languageDescriptionMediaTypeType'
    __schema_fields__ = (
        (u'languageDescriptionTextInfo', u'languageDescriptionTextInfo', RECOMMENDED),
    )
    __schema_classes__ = {
        u'languageDescriptionTextInfo': "languageDescriptionTextInfoType_model",
    }

    languageDescriptionTextInfo = models.OneToOneField("languageDescriptionTextInfoType_model",
                                                       verbose_name='Language description text component',
                                                       help_text='Groups together all information relevant to the text mo' \
                                                                 'dule of a language description (e.g. format, languages, size etc.' \
                                                                 '); it is obligatory for all language descriptions',
                                                       blank=True, null=True, on_delete=models.SET_NULL, )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class lexicalConceptualResourceMediaTypeType_model(SchemaModel):
    class Meta:
        verbose_name = "Lexical conceptual resource media"

    __schema_name__ = 'lexicalConceptualResourceMediaTypeType'
    __schema_fields__ = (
        (u'lexicalConceptualResourceTextInfo', u'lexicalConceptualResourceTextInfo', RECOMMENDED),
    )
    __schema_classes__ = {
        u'lexicalConceptualResourceTextInfo': "lexicalConceptualResourceTextInfoType_model",
    }

    lexicalConceptualResourceTextInfo = models.OneToOneField("lexicalConceptualResourceTextInfoType_model",
                                                             verbose_name='Lexical / Conceptual resource text component',
                                                             help_text='Groups information on the textual part of the lexical/c' \
                                                                       'onceptual resource',
                                                             blank=True, null=True, on_delete=models.SET_NULL, )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


DOMAINSETINFOTYPE_DOMAIN_CHOICES = _make_choices_from_list([
    u'POLITICS', u'INTERNATIONAL RELATIONS', u'EUROPEAN UNION', u'LAW',
    u'ECONOMICS', u'TRADE', u'FINANCE', u'SOCIAL QUESTIONS',
    u'EDUCATION AND COMMUNICATIONS', u'SCIENCE', u'BUSINESS AND COMPETITION',
    u'EMPLOYMENT AND WORKING CONDITIONS', u'TRANSPORT', u'ENVIRONMENT',
    u'AGRICULTURE, FORESTRY AND FISHERIES', u'AGRI-FOODSTUFFS',
    u'PRODUCTION, TECHNOLOGY AND RESEARCH', u'ENERGY', u'INDUSTRY',
    u'GEOGRAPHY', u'INTERNATIONAL ORGANISATIONS',
])

DOMAINSETINFOTYPE_DOMAINID_CHOICES = _make_choices_from_list([
    u'04', u'06', u'10', u'12', u'16', u'20', u'24', u'28', u'32', u'36',
    u'40', u'44', u'48', u'52', u'56', u'60', u'64', u'66', u'68', u'72',
    u'76',
])


# pylint: disable-msg=C0103
class domainSetInfoType_model(SchemaModel):
    class Meta:
        verbose_name = "Domain set"

    __schema_name__ = 'domainSetInfoType'
    __schema_fields__ = (
        (u'domain', u'domain', REQUIRED),
        (u'domainId', u'domainId', REQUIRED),
        (u'subdomain', u'subdomain', OPTIONAL),
        (u'subdomainId', u'subdomainId', OPTIONAL),
        (u'conformanceToClassificationScheme', u'conformanceToClassificationScheme', OPTIONAL),
    )

    domain = MultiSelectField(
        verbose_name='Domain',
        help_text='Specifies the application domain of the resource or the' \
                  ' tool/service',

        max_length=1 + len(DOMAINSETINFOTYPE_DOMAIN_CHOICES['choices']) / 4,
        choices=DOMAINSETINFOTYPE_DOMAIN_CHOICES['choices'],
    )

    domainId = MultiSelectField(
        verbose_name='Domain identifier',
        help_text='Specifies the application domain of the resource or the' \
                  ' tool/service',

        max_length=1 + len(DOMAINSETINFOTYPE_DOMAINID_CHOICES['choices']) / 4,
        choices=DOMAINSETINFOTYPE_DOMAINID_CHOICES['choices'],
    )

    subdomain = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=29, max_length=1000),
                               verbose_name='Subdomain',
                               help_text='The name of the application subdomain of the resource o' \
                                         'r the tool/service, taken from the EUROVOC domains: http://eurovo' \
                                         'c.europa.eu/drupal',
                               blank=True, validators=[validate_matches_xml_char_production], )

    subdomainId = MultiTextField(max_length=1000, widget=MultiFieldWidget(widget_id=30, max_length=1000),
                                 verbose_name='Subdomain identifier',
                                 help_text='The identifier of the application subdomain of the reso' \
                                           'urce or the tool/service, taken from the EUROVOC domains: http://' \
                                           'eurovoc.europa.eu/drupal',
                                 blank=True, validators=[validate_matches_xml_char_production], )

    conformanceToClassificationScheme = XmlCharField(
        verbose_name='Conformance to classification scheme',
        help_text='Specifies the external classification schemes',
        blank=True, max_length=1000, )

    def __unicode__(self):
        _unicode = u'<{} id="{}">'.format(self.__schema_name__, self.id)
        return _unicode


# pylint: disable-msg=C0103
class documentUnstructuredString_model(documentationInfoType_model):
    """
    Is a xs:string choice: a field whose relation name will not be rendered
    and has special im-/export functionality
    """
    __schema_name__ = 'STRINGMODEL'

    value = models.TextField(null=True)

    def __unicode__(self):
        return self.value if self.value else u''
