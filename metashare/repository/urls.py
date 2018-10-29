from django.conf.urls import patterns, url, include

from haystack.views import search_view_factory
from haystack.query import SearchQuerySet

from metashare.repository.forms import FacetedBrowseForm
from metashare.repository.views import MetashareFacetedSearchView

from tastypie.api import Api
from metashare.repository.api.resources import LrResource, MetadataInfoResource

sqs = SearchQuerySet() \
    .facet("languageNameFilter") \
    .facet("resourceTypeFilter") \
    .facet("mediaTypeFilter") \
    .facet("licenceFilter") \
    .facet("restrictionsOfUseFilter") \
    .facet("validatedFilter") \
    .facet("useNlpSpecificFilter") \
    .facet("lingualityTypeFilter") \
    .facet("multilingualityTypeFilter") \
    .facet("modalityTypeFilter") \
    .facet("dataFormatFilter") \
    .facet("domainFilter") \
    .facet("corpusAnnotationTypeFilter") \
    .facet("languageDescriptionLDTypeFilter") \
    .facet("languageDescriptionEncodingLevelFilter") \
    .facet("languageDescriptionGrammaticalPhenomenaCoverageFilter") \
    .facet("lexicalConceptualResourceLRTypeFilter") \
    .facet("lexicalConceptualResourceEncodingLevelFilter") \
    .facet("lexicalConceptualResourceLinguisticInformationFilter") \
    .facet("toolServiceToolServiceTypeFilter") \
    .facet("toolServiceToolServiceSubTypeFilter") \
    .facet("toolServiceLanguageDependentTypeFilter") \
    .facet("toolServiceInputOutputResourceTypeFilter") \
    .facet("toolServiceInputOutputMediaTypeFilter") \
    .facet("toolServiceAnnotationTypeFilter") \
    .facet("textTextGenreFilter") \
    .facet("textTextTypeFilter") \
    .facet("appropriatenessForDSIFilter") \
    .facet("publicationStatusFilter") \
    .facet("processabilityFilter")
    # .facet("availabilityFilter") \
    # .facet("bestPracticesFilter") \
    # .facet("languageVarietyFilter") \

v1_api = Api(api_name='v1')
v1_api.register(LrResource())
v1_api.register(MetadataInfoResource())

urlpatterns = patterns('metashare.repository.views',
                       url(r'^browse/(?P<resource_name>[\w\-]*)/(?P<object_id>\w+)/$',
                           'view', name='browse'),
                       url(r'^browse/(?P<object_id>\w+)/$',
                           'view', name='browse'),
                       url(r'^download/(?P<object_id>\w+)/$',
                           'download', name='download'),
                       url(r'^download_contact/(?P<object_id>\w+)/$',
                           'download_contact', name='download_contact'),
                       url(r'^search/$',
                           search_view_factory(view_class=MetashareFacetedSearchView,
                                               form_class=FacetedBrowseForm,
                                               template='repository/search.html',
                                               searchqueryset=sqs)),
                       url(r'api/', include(v1_api.urls)),
                       url(r'contribute', 'contribute', name='contribute'),
                       url(r'contributions', 'manage_contributed_data', name='manage_contributed_data'),
                       url(r'repo_report', 'repo_report'),
                       url(r'report_extended', 'report_extended'),
                       url(r'addtodb/$', 'addtodb', name='addtodb'),
                       url(r'get_data/(?P<filename>.+\.zip)', 'get_data', name='get_data'),
                       url(r'^processing/', include('metashare.processing.urls')),
                       )
