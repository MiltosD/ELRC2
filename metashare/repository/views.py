from distutils import util
import json
import logging
import os
import shutil
import uuid

from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from haystack.query import SearchQuerySet
from metashare.report_utils.report_utils import _is_processed, _is_not_processed_or_related, _get_country, \
    _get_resource_mimetypes, _get_resource_linguality, _get_resource_lang_info, _get_resource_sizes, \
    _get_resource_lang_sizes, _get_preferred_size, _get_resource_domain_info
from metashare.repository.export_utils import xml_to_json
from metashare.repository.templatetags.is_member import is_member
from django.http import JsonResponse
from collections import OrderedDict

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.utils.encoding import smart_str
from lxml import etree

import dicttoxml
import requests

import xlsxwriter
import datetime
from os.path import split, getsize
from mimetypes import guess_type

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.files import File
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseNotFound, StreamingHttpResponse
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.template.loader import render_to_string
from django.core.mail import send_mail, EmailMessage
from django.utils.translation import ugettext as _

from haystack.views import FacetedSearchView

from metashare.accounts.models import UserProfile
from metashare.local_settings import CONTRIBUTIONS_ALERT_EMAILS, TMP
from metashare.recommendations.recommendations import SessionResourcesTracker, \
    get_download_recommendations, get_view_recommendations, \
    get_more_from_same_creators_qs, get_more_from_same_projects_qs
from metashare.repository import model_utils
from metashare.repository.editor.resource_editor import has_edit_permission
from metashare.repository.forms import LicenseSelectionForm, \
    LicenseAgreementForm, DownloadContactForm, MORE_FROM_SAME_CREATORS, \
    MORE_FROM_SAME_PROJECTS
from metashare.repository.models import resourceInfoType_model, identificationInfoType_model, \
    communicationInfoType_model, organizationInfoType_model, personInfoType_model, corpusMediaTypeType_model, \
    corpusTextInfoType_model, lingualityInfoType_model, languageInfoType_model, corpusInfoType_model, \
    metadataInfoType_model, languageDescriptionTextInfoType_model, languageDescriptionMediaTypeType_model, \
    languageDescriptionInfoType_model, lexicalConceptualResourceTextInfoType_model, \
    lexicalConceptualResourceMediaTypeType_model, lexicalConceptualResourceInfoType_model, distributionInfoType_model, \
    licenceInfoType_model, resourceCreationInfoType_model
from metashare.repository.search_indexes import resourceInfoType_modelIndex, \
    update_lr_index_entry
from metashare.settings import LOG_HANDLER, STATIC_URL, DJANGO_URL, MAXIMUM_UPLOAD_SIZE, CONTRIBUTION_FORM_DATA, \
    ROOT_PATH
from metashare.stats.model_utils import getLRStats, saveLRStats, \
    saveQueryStats, VIEW_STAT, DOWNLOAD_STAT
from metashare.storage.models import PUBLISHED, INGESTED
from metashare.utils import prettify_camel_case_string
from decorators import resource_downloadable, resource_downloadable_view

MAXIMUM_READ_BLOCK_SIZE = 4096

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)


def _convert_to_template_tuples(element_tree):
    """
    Converts the given ElementTree instance to template tuples.

    A template tuple contains:
    - a two-tuple (component, values) for complex nodes, and
    - a one-tuple ((key, value),) for simple tags.

    The length distinction allows for recursive rendering in the template.
    See repository/detail.html and repository/detail_view.html for more information.

    Rendering recursively inside the Django template system needs this trick:
    - http://blog.elsdoerfer.name/2008/01/22/recursion-in-django-templates/

    """
    # If we are dealing with a complex node containing children nodes, we have
    # to first recursively collect the data values from the sub components.
    if len(element_tree):
        values = []
        for child in element_tree:
            values.append(_convert_to_template_tuples(child))
        # use pretty print name of element instead of tag; requires that 
        # element_tree is created using export_to_elementtree(pretty=True)
        return (element_tree.attrib["pretty"], values)

    # Otherwise, we return a tuple containg (key, value, required), 
    # i.e., (tag, text, <True,False>).
    # The "required" element was added to the tree, for passing 
    # information about whether a field is required or not, to correctly
    # render the single resource view.
    else:
        # use pretty print name of element instead of tag; requires that 
        # element_tree is created using export_to_elementtree(pretty=True)
        return ((element_tree.attrib["pretty"], element_tree.text),)


# a type providing an enumeration of META-SHARE member types
MEMBER_TYPES = type('MemberEnum', (), dict(GOD=100, FULL=3, ASSOCIATE=2, NON=1))

# a dictionary holding a URL for each download licence and a member type which
# is required at a minimum to be able to download the associated resource
# straight away; otherwise the licence requires a hard-copy signature
LICENCEINFOTYPE_URLS_LICENCE_CHOICES = {
    'CC-BY-4.0': (STATIC_URL + 'metashare/licences/CC-BY-4.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-4.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-4.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-ND-4.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-ND-4.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-SA-4.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-SA-4.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-ND-4.0': (STATIC_URL + 'metashare/licences/CC-BY-ND-4.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-SA-4.0': (STATIC_URL + 'metashare/licences/CC-BY-SA-4.0.pdf', MEMBER_TYPES.NON),
    'CC0-1.0': (STATIC_URL + 'metashare/licences/CC0-1.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-3.0': (STATIC_URL + 'metashare/licences/CC-BY-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-3.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-ND-3.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-ND-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-SA-3.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-SA-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-ND-3.0': (STATIC_URL + 'metashare/licences/CC-BY-ND-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-SA-3.0': (STATIC_URL + 'metashare/licences/CC-BY-SA-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-2.0': (STATIC_URL + 'metashare/licences/CC-BY-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-2.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-ND-2.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-ND-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-SA-2.0': (STATIC_URL + 'metashare/licences/CC-BY-NC-SA-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-ND-2.0': (STATIC_URL + 'metashare/licences/CC-BY-ND-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-SA-2.0': (STATIC_URL + 'metashare/licences/CC-BY-SA-3.0.pdf', MEMBER_TYPES.NON),
    'CC-BY-SA-2.5_Sl': (STATIC_URL + 'metashare/licences/CC-BY-SA-2.5_Sl.pdf', MEMBER_TYPES.NON),
    'CC-BY-3.0-AT': (STATIC_URL + 'metashare/licences/CC-BY-3.0-AT.pdf', MEMBER_TYPES.NON),
    'CC-BY-3.0-CZ': (STATIC_URL + 'metashare/licences/CC-BY-3.0-CZ.pdf', MEMBER_TYPES.NON),
    'CC-BY-2.5-SE': (STATIC_URL + 'metashare/licences/CC-BY-2.5-SE.pdf', MEMBER_TYPES.NON),
    'CC-BY-3.0-IT': (STATIC_URL + 'metashare/licences/CC-BY-3.0-IT.pdf', MEMBER_TYPES.NON),
    'CC-BY-SA-3.0-PL': (STATIC_URL + 'metashare/licences/CC-BY-SA-3.0-PL.pdf', MEMBER_TYPES.NON),
    'CC-BY-NC-SA-3.0-PL': (STATIC_URL + 'metashare/licences/CC-BY-NC-SA-3.0-PL.pdf', MEMBER_TYPES.NON),

    # TODO: PDDL
    'PDDL-1.0': (STATIC_URL + 'metashare/licences/PDDL-1.0.pdf', MEMBER_TYPES.NON),
    # TODO: ODC-BY
    'ODC-BY-1.0': (STATIC_URL + 'metashare/licences/ODC-BY-1.0.pdf', MEMBER_TYPES.NON),
    'ODbL-1.0': (STATIC_URL + 'metashare/licences/ODbL-1.0.pdf', MEMBER_TYPES.NON),
    'AGPL-3.0': (STATIC_URL + 'metashare/licences/AGPL-3.0.pdf', MEMBER_TYPES.NON),
    'Apache-2.0': (STATIC_URL + 'metashare/licences/Apache-2.0.pdf', MEMBER_TYPES.NON),
    'BSD-4-Clause': (STATIC_URL + 'metashare/licences/BSD-4-Clause.pdf', MEMBER_TYPES.NON),
    'BSD-3-Clause': (STATIC_URL + 'metashare/licences/BSD-3-Clause.pdf', MEMBER_TYPES.NON),
    'BSD-2-Clause': (STATIC_URL + 'metashare/licences/BSD-2-Clause', MEMBER_TYPES.NON),
    'GFDL-1.3': (STATIC_URL + 'metashare/licences/GFDL-1.3.pdf', MEMBER_TYPES.NON),
    'GPL-2.0': (STATIC_URL + 'metashare/licences/GPL-2.0.pdf', MEMBER_TYPES.NON),
    'GPL-3.0': (STATIC_URL + 'metashare/licences/GPL-3.0.pdf', MEMBER_TYPES.NON),
    'LGPL-2.1': (STATIC_URL + 'metashare/licences/LGPL-2.1.pdf', MEMBER_TYPES.NON),
    'LGPL-3.0': (STATIC_URL + 'metashare/licences/LGPL-3.0.pdf', MEMBER_TYPES.NON),
    'MIT': (STATIC_URL + 'metashare/licences/MIT.pdf', MEMBER_TYPES.NON),
    'EPL-1.0': (STATIC_URL + 'metashare/licences/EPL-1.0.pdf', MEMBER_TYPES.NON),
    'EUPL-1.0': (STATIC_URL + 'metashare/licences/EUPL-1.0.pdf', MEMBER_TYPES.NON),
    'EUPL-1.1': (STATIC_URL + 'metashare/licences/EUPL-1.1.pdf', MEMBER_TYPES.NON),
    'EUPL-1.2': (STATIC_URL + 'metashare/licences/EUPL-1.2.pdf', MEMBER_TYPES.NON),
    'LO-OL-v2': (STATIC_URL + 'metashare/licences/LO-OL-v2.pdf', MEMBER_TYPES.NON),
    'dl-de/by-2-0': (STATIC_URL + 'metashare/licences/dl-de_by-2-0.pdf', MEMBER_TYPES.NON),
    'dl-de/zero-2-0': (STATIC_URL + 'metashare/licences/dl-de_zero-2-0.pdf', MEMBER_TYPES.NON),
    'IODL-1.0': (STATIC_URL + 'metashare/licences/IODL-1.0.pdf', MEMBER_TYPES.NON),
    'NLOD-1.0': (STATIC_URL + 'metashare/licences/NLOD-1.0.pdf', MEMBER_TYPES.NON),
    'OGL-UK-3.0': (STATIC_URL + 'metashare/licences/OGL-UK-3.0.pdf', MEMBER_TYPES.NON),
    'OGL-UK-2.0': (STATIC_URL + 'metashare/licences/OGL-UK-2.0.pdf', MEMBER_TYPES.NON),
    'OGL-UK-1.0': (STATIC_URL + 'metashare/licences/OGL-UK-1.0.pdf', MEMBER_TYPES.NON),
    'OGL-CA-2.0': (STATIC_URL + 'metashare/licences/OGL-CA-2.0.pdf', MEMBER_TYPES.NON),
    'NCGL-1.0': (STATIC_URL + 'metashare/licences/NCGL-1.0.pdf', MEMBER_TYPES.GOD),
    'openUnder-PSI': ('', MEMBER_TYPES.NON),
    'publicDomain': ('', MEMBER_TYPES.NON),
    'non-standard/Other_Licence/Terms': ('', MEMBER_TYPES.NON),
    'underReview': ('', MEMBER_TYPES.GOD),
}


def _get_user_membership(user):
    """
    Returns a `MEMBER_TYPES` type based on the permissions of the given
    authenticated user. 
    """
    if user.has_perm('accounts.ms_full_member'):
        return MEMBER_TYPES.FULL
    elif user.has_perm('accounts.ms_associate_member'):
        return MEMBER_TYPES.ASSOCIATE
    return MEMBER_TYPES.NON


def _get_licences(resource, user_membership):
    """
    Returns the licences under which a download/purchase of the given resource
    is possible for the given user membership.
    
    The result is a dictionary mapping from licence names to pairs. Each pair
    contains the corresponding `licenceInfoType_model`, the download location
    URLs and a boolean denoting whether the resource may (and can) be directly
    downloaded or if there need to be further negotiations of some sort.
    """
    distribution_infos = tuple(resource.distributioninfotype_model_set.all())

    # licence_infos = tuple([(l_info, d_info.downloadLocation + d_info.executionLocation) \
    licence_infos = tuple([(l_info, d_info.downloadLocation + d_info.executionLocation) \
                           for d_info in distribution_infos for l_info in d_info.licenceInfo.all()])

    all_licenses = dict([(l_info.licence, (l_info, access_links)) \
                         for l_info, access_links in licence_infos])
    result = {}
    for name, info in all_licenses.items():
        l_info, access_links = info
        access = LICENCEINFOTYPE_URLS_LICENCE_CHOICES.get(name, None)
        if access == None:
            LOGGER.warn("Unknown license name discovered in the database for " \
                        "object #{}: {}".format(resource.id, name))
            del all_licenses[name]
        elif user_membership >= access[1] \
                and (len(access_links) or resource.storage_object.get_download()):
            # the resource can be downloaded somewhere under the current license
            # terms and the user's membership allows her to immediately download
            # the resource
            result[name] = (l_info, access_links, True)
        else:
            # further negotiations are required with the current license
            result[name] = (l_info, access_links, False)
    return result


# @user_passes_test(lambda u: u.is_superuser or u.groups.filter(name="ecmembers").exists())
# MDEL: temporary implementation to provide download for specific resources
@resource_downloadable
def download(request, object_id, **kwargs):
    """
    Renders the resource download/purchase view including license selection,
    etc.
    """
    user_membership = _get_user_membership(request.user)
    bypass_licence = False
    api_auth = kwargs.get('api_auth', None)
    if request.user.is_superuser \
            or request.user.groups.filter(name="ecmembers").exists() \
            or request.user.groups.filter(name="elrcReviewers").exists()\
            or api_auth:
        bypass_licence = True

    # here we are only interested in licenses (or their names) of the specified
    # resource that allow the current user a download/purchase
    resource = get_object_or_404(resourceInfoType_model,
                                 storage_object__identifier=object_id,
                                 storage_object__deleted=False)
    # Get a dictionary, where the values are triplets:
    # (licenceInfo instance, download location, access)
    licences = _get_licences(resource, user_membership)

    # Check whether the resource is from the current node, or whether it must be
    # redirected to the master copy
    if not resource.storage_object.master_copy:
        return render_to_response('repository/redirect.html',
                                  {'resource': resource,
                                   'redirection_url': model_utils.get_lr_master_url(resource)},
                                  context_instance=RequestContext(request))

    licence_choice = None

    # if the user is superuser or in ecmembers group, provide download directly bypassing licensing and stats
    if request.method == "GET" and bypass_licence:
        return _provide_download(request, resource, None, bypass_licence)

    if request.method == "POST":
        licence_choice = request.POST.get('licence', None)
        if licence_choice and 'in_licence_agree_form' in request.POST:
            la_form = LicenseAgreementForm(licence_choice, data=request.POST)
            l_info, access_links, access = licences[licence_choice]
            if la_form.is_valid():
                # before really providing the download, we have to make sure
                # that the user hasn't tried to circumvent the permission system
                if access:
                    return _provide_download(request, resource, access_links, False)
            else:
                _dict = {'form': la_form,
                         'resource': resource,
                         'licence_name': licence_choice,
                         'licence_path': LICENCEINFOTYPE_URLS_LICENCE_CHOICES[licence_choice][0],
                         'download_available': access,
                         'l_name': l_info.otherLicenceName,
                         'l_url': l_info.otherLicence_TermsURL,
                         'l_text': l_info.otherLicence_TermsText.values()}
                return render_to_response('repository/licence_agreement.html',
                                          _dict, context_instance=RequestContext(request))
        elif licence_choice and not licence_choice in licences:
            licence_choice = None

    if len(licences) == 1:
        # no need to manually choose amongst 1 license ...
        licence_choice = licences.iterkeys().next()

    if licence_choice:
        l_info, access_links, access = licences[licence_choice]
        _dict = {'form': LicenseAgreementForm(licence_choice),
                 'resource': resource, 'licence_name': licence_choice,
                 'licence_path': LICENCEINFOTYPE_URLS_LICENCE_CHOICES[licence_choice][0],
                 'download_available': access,
                 'l_name': l_info.otherLicenceName,
                 'l_url': l_info.otherLicence_TermsURL,
                 'l_text': l_info.otherLicence_TermsText.values(),
                 'l_conditions': l_info.restrictionsOfUse}
        return render_to_response('repository/licence_agreement.html',
                                  _dict, context_instance=RequestContext(request))
    elif len(licences) > 1:
        return render_to_response('repository/licence_selection.html',
                                  {'form': LicenseSelectionForm(licences),
                                   'resource': resource},
                                  context_instance=RequestContext(request))
    else:
        return render_to_response('repository/lr_not_downloadable.html',
                                  {'resource': resource,
                                   'reason': 'no_suitable_license'},
                                  context_instance=RequestContext(request))


def _provide_download(request, resource, access_links, bypass_stats):
    """
    Returns an HTTP response with a download of the given resource.
    """
    dl_path = resource.storage_object.get_download()
    if dl_path:
        try:
            def dl_stream_generator():
                with open(dl_path, 'rb') as _local_data:
                    _chunk = _local_data.read(MAXIMUM_READ_BLOCK_SIZE)
                    while _chunk:
                        yield _chunk
                        _chunk = _local_data.read(MAXIMUM_READ_BLOCK_SIZE)

            # build HTTP response with a guessed mime type; the response
            # content is a stream of the download file
            filemimetype = guess_type(dl_path)[0] or "application/octet-stream"
            response = StreamingHttpResponse(dl_stream_generator(),
                                    content_type=filemimetype)
            response['Content-Length'] = getsize(dl_path)
            response['Content-Disposition'] = 'attachment; filename={0}' \
                .format(split(dl_path)[1])
            if not bypass_stats:
                _update_download_stats(resource, request)
            LOGGER.info("Offering a local download of resource #{0}." \
                        .format(resource.id))
            return response
        except:
            LOGGER.warn("An error has occurred while trying to provide the " \
                        "local download copy of resource #{0}." \
                        .format(resource.id))
    # redirect to a download location, if available
    elif access_links:
        for url in access_links:
            try:
                req = requests.request('GET', url)
            except:
                LOGGER.warn("No download could be offered for resource #{0}. The " \
                            "URL {1} was tried: {1}".format(resource.id, url), exc_info=True)
                continue
            if req.status_code == requests.codes.ok:
                _update_download_stats(resource, request)
                LOGGER.info("Redirecting to {0} for the download of resource " \
                            "#{1}.".format(url, resource.id))
                return redirect(url)
        LOGGER.warn("No download could be offered for resource #{0}. These " \
                    "URLs were tried: {1}".format(resource.id, access_links))
    else:
        LOGGER.error("No download could be offered for resource #{0} with " \
                     "storage object identifier #{1} although our code " \
                     "considered it to be downloadable!".format(resource.id,
                                                                resource.storage_object.identifier))

    # no download could be provided
    return render_to_response('repository/lr_not_downloadable.html',
                              {'resource': resource, 'reason': 'internal'},
                              context_instance=RequestContext(request))


def _update_download_stats(resource, request):
    """
    Updates all relevant statistics counters for a the given successful resource
    download request.
    """
    # maintain general download statistics
    if saveLRStats(resource, DOWNLOAD_STAT, request):
        # update download count in the search index, too
        update_lr_index_entry(resource)
    # update download tracker
    tracker = SessionResourcesTracker.getTracker(request)
    tracker.add_download(resource, datetime.datetime.now())
    request.session['tracker'] = tracker


@login_required
def download_contact(request, object_id):
    """
    Renders the download contact view to request information regarding a resource
    """
    resource = get_object_or_404(resourceInfoType_model,
                                 storage_object__identifier=object_id,
                                 storage_object__publication_status=PUBLISHED)

    default_message = "We are interested in using the above mentioned " \
                      "resource. Please provide us with all the relevant information (e.g.," \
                      " licensing provisions and restrictions, any fees required etc.) " \
                      "which is necessary for concluding a deal for getting a license. We " \
                      "are happy to provide any more information on our request and our " \
                      "envisaged usage of your resource.\n\n" \
                      "[Please include here any other request you may have regarding this " \
                      "resource or change this message altogether]\n\n" \
                      "Please kindly use the above mentioned e-mail address for any " \
                      "further communication."

    # Find out the relevant resource contact emails and names
    resource_emails = []
    resource_contacts = []
    for person in resource.contactPerson.all():
        resource_emails.append(person.communicationInfo.email[0])
        if person.givenName:
            _name = u'{} '.format(person.get_default_givenName())
        else:
            _name = u''
        resource_contacts.append(_name + person.get_default_surname())

    # Check if the edit form has been submitted.
    if request.method == "POST":
        # If so, bind the creation form to HTTP POST values.
        form = DownloadContactForm(initial={'userEmail': request.user.email,
                                            'message': default_message},
                                   data=request.POST)
        # Check if the form has validated successfully.
        if form.is_valid():
            message = form.cleaned_data['message']
            user_email = form.cleaned_data['userEmail']

            # Render notification email template with correct values.
            data = {'message': message, 'resource': resource,
                    'resourceContactName': resource_contacts, 'user': request.user,
                    'user_email': user_email, 'node_url': DJANGO_URL}
            try:
                # Send out email to the resource contacts
                send_mail('Request for information regarding a resource',
                          render_to_string('repository/' \
                                           'resource_download_information.email', data),
                          user_email, resource_emails, fail_silently=False)
            except:  # SMTPException:
                # If the email could not be sent successfully, tell the user
                # about it.
                messages.error(request,
                               _("There was an error sending out the request email."))
            else:
                messages.success(request, _('You have successfully ' \
                                            'sent a message to the resource contact person.'))

            # Redirect the user to the resource page.
            return redirect(resource.get_absolute_url())

    # Otherwise, render a new DownloadContactForm instance
    else:
        form = DownloadContactForm(initial={'userEmail': request.user.email,
                                            'message': default_message})

    dictionary = {'username': request.user,
                  'resource': resource,
                  'resourceContactName': resource_contacts,
                  'resourceContactEmail': resource_emails,
                  'form': form}
    return render_to_response('repository/download_contact_form.html',
                              dictionary, context_instance=RequestContext(request))


def has_view_permission(request, res_obj):
    """
    Returns `True` if the given request has permission to view the description
    of the current resource, `False` otherwise.
    """
    if res_obj.storage_object.publication_status == PUBLISHED:
        return True
    else:
        if request.user.is_superuser \
                or request.user.groups.filter(name='ecmembers').exists() \
                or request.user.groups.filter(name='elrcReviewers').exists():
            return True

        return False


# MDEL: temporary implementation to provide download for specific resources
@resource_downloadable_view
def view(request, resource_name=None, object_id=None):
    """
    Render browse or detail view for the repository application.
    """
    # only published resources may be viewed. Ingested LRs can be viewed only
    # by EC members and technical reviewers
    resource = get_object_or_404(resourceInfoType_model,
                                 storage_object__identifier=object_id,
                                 storage_object__publication_status__in=[INGESTED, PUBLISHED])

    if not has_view_permission(request, resource):
        raise PermissionDenied

    if request.path_info != resource.get_absolute_url():
        return redirect(resource.get_absolute_url())

    # Convert resource to ElementTree and then to template tuples.
    lr_content = _convert_to_template_tuples(
        resource.export_to_elementtree(pretty=True))

    # get the 'best' language version of a "DictField" and all other versions
    resource_name = resource.identificationInfo.get_default_resourceName()
    res_short_names = resource.identificationInfo.resourceShortName.values()
    description = resource.identificationInfo.get_default_description()
    other_res_names = [name for name in resource.identificationInfo \
        .resourceName.itervalues() if name != resource_name]
    other_descriptions = [name for name in resource.identificationInfo \
        .description.itervalues() if name != description]

    # Create fields lists
    url = resource.identificationInfo.url
    metashare_id = resource.identificationInfo.metaShareId
    identifier = resource.identificationInfo.identifier
    islrn = resource.identificationInfo.ISLRN
    dsi = resource.identificationInfo.appropriatenessForDSI
    is_processable = model_utils.is_processable(resource)
    resource_type = resource.resourceComponentType.as_subclass().resourceType
    media_types = set(model_utils.get_resource_media_types(resource))
    linguality_infos = set(model_utils.get_resource_linguality_infos(resource))
    license_types = set(model_utils.get_resource_license_types(resource))

    distribution_info_tuple = None
    attribution_details = model_utils.get_resource_attribution_texts(resource)
    distribution_info_tuples = []
    contact_person_tuples = []
    metadata_info_tuple = None
    version_info_tuple = None
    validation_info_tuples = []
    usage_info_tuple = None
    documentation_info_tuple = None
    resource_creation_info_tuple = None
    relation_info_tuples = []
    resource_component_tuple = None
    for _tuple in lr_content[1]:
        if _tuple[0] == "Distribution":
            distribution_info_tuples.append(_tuple)
        elif _tuple[0] == "Contact person":
            contact_person_tuples.append(_tuple)
        elif _tuple[0] == "Metadata":
            metadata_info_tuple = _tuple
        elif _tuple[0] == "Version":
            version_info_tuple = _tuple
        elif _tuple[0] == "Validation":
            validation_info_tuples.append(_tuple)
        elif _tuple[0] == "Usage":
            usage_info_tuple = _tuple
        elif _tuple[0] == "Resource documentation":
            documentation_info_tuple = _tuple
        elif _tuple[0] == "Resource creation":
            resource_creation_info_tuple = _tuple
        elif _tuple[0] == "Relation":
            relation_info_tuples.append(_tuple)
        elif _tuple[0] == "Resource component type":
            resource_component_tuple = _tuple[1]

    # Convert resource_component_tuple to nested dictionaries
    resource_component_dicts = {}
    validation_dicts = []
    relation_dicts = []

    # Convert several tuples to dictionaries to facilitate rendering
    # the templates.
    contact_person_dicts = []
    distribution_dicts = []
    for item in contact_person_tuples:
        contact_person_dicts.append(tuple2dict([item]))
    for item in distribution_info_tuples:
        distribution_dicts.append(tuple2dict([item]))
    resource_component_dict = tuple2dict(resource_component_tuple)
    resource_creation_dict = tuple2dict([resource_creation_info_tuple])
    metadata_dict = tuple2dict([metadata_info_tuple])
    usage_dict = tuple2dict([usage_info_tuple])
    version_dict = tuple2dict([version_info_tuple])
    documentation_dict = tuple2dict([documentation_info_tuple])
    for item in validation_info_tuples:
        validation_dicts.append(tuple2dict([item]))
    for item in relation_info_tuples:
        relation_dicts.append(tuple2dict([item]))

    # Count individual media resource components
    text_counts = []
    video_counts = []
    if resource_type == "corpus":
        for key, value in resource_component_dict['Resource_component_type']['Media_type_component_of_corpus'].items():
            if "Corpus_text" in key and not "numerical" in key and not "ngram" in key:
                text_counts.append(value)
            elif "Corpus_video" in key:
                video_counts.append(value)

    # Create a list of resource components dictionaries
    if resource_type == "corpus":
        for media_type in media_types:
            if media_type == "text":
                resource_component_dicts['text'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_corpus']['Corpus_text']
            if media_type == "audio":
                resource_component_dicts['audio'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_corpus']['Corpus_audio_component']
            if media_type == "video":
                resource_component_dicts['video'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_corpus']['Corpus_video']
            if media_type == "image":
                resource_component_dicts['image'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_corpus']['Corpus_image_component']
            if media_type == "textNgram":
                resource_component_dicts['textNgram'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_corpus']['Corpus_textNgram']
            if media_type == "textNumerical":
                resource_component_dicts['textNumerical'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_corpus']['Corpus_textNumerical']

    elif resource_type == "languageDescription":
        for media_type in media_types:
            if media_type == "text":
                resource_component_dicts['text'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_language_description']['Language_description_text_component']
            if media_type == "image":
                resource_component_dicts['image'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_language_description']['Language_description_image_component']
            if media_type == "video":
                resource_component_dicts['video'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_language_description']['Language_description_video_component']

    elif resource_type == "lexicalConceptualResource":
        for media_type in media_types:
            if media_type == "text":
                resource_component_dicts['text'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_lexical___conceptual_resource'] \
                        ['Lexical___Conceptual_resource_text_component']
            if media_type == "audio":
                resource_component_dicts['audio'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_lexical___conceptual_resource'] \
                        ['Lexical___Conceptual_resource_audio_component']
            if media_type == "video":
                resource_component_dicts['video'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_lexical___conceptual_resource'] \
                        ['Lexical___Conceptual_resource_video_component']
            if media_type == "image":
                resource_component_dicts['image'] = \
                    resource_component_dict['Resource_component_type'] \
                        ['Media_type_component_of_lexical___conceptual_resource'] \
                        ['Lexical___Conceptual_resource_image_component']

    elif resource_type == "toolService":
        resource_component_dicts['toolService'] = \
            resource_component_dict['Resource_component_type']

    # Define context for template rendering.
    context = {
        'contact_person_dicts': contact_person_dicts,
        'description': description,
        'distribution_dicts': distribution_dicts,
        'documentation_dict': documentation_dict,
        'license_types': license_types,
        'linguality_infos': linguality_infos,
        'mediaTypes': media_types,
        'metadata_dict': metadata_dict,
        'metaShareId': metashare_id,
        'identifier': identifier,
        'islrn': islrn,
        'dsi': dsi,
        'processable': True if is_processable[0] == 'YES' else False,
        'fully_processable': is_processable[1],
        'other_res_names': other_res_names,
        'other_descriptions': other_descriptions,
        'relation_dicts': relation_dicts,
        'res_short_names': res_short_names,
        'resource': resource,
        'resource_component_dicts': resource_component_dicts,
        'resource_component_dict': resource_component_dict,
        'resourceName': resource_name,
        'attribution_details': attribution_details,
        'resourceType': resource_type,
        'resource_creation_dict': resource_creation_dict,
        'url': url,
        'usage_dict': usage_dict,
        'validation_dicts': validation_dicts,
        'version_dict': version_dict,
        'text_counts': text_counts,
        'video_counts': video_counts,
    }
    template = 'repository/resource_view/lr_view.html'

    # For users who have edit permission for this resource, we have to add 
    # LR_EDIT which contains the URL of the Django admin backend page 
    # for this resource.
    if has_edit_permission(request, resource):
        context['LR_EDIT'] = reverse(
            'admin:repository_resourceinfotype_model_change', \
            args=(resource.id,))

    # Update statistics:
    if saveLRStats(resource, VIEW_STAT, request):
        # update view count in the search index, too
        update_lr_index_entry(resource)
    # update view tracker
    tracker = SessionResourcesTracker.getTracker(request)
    tracker.add_view(resource, datetime.datetime.now())
    request.session['tracker'] = tracker

    # Add download/view/last updated statistics to the template context.
    context['LR_STATS'] = getLRStats(resource.storage_object.identifier)

    # Add recommendations for 'also viewed' resources
    context['also_viewed'] = \
        _format_recommendations(get_view_recommendations(resource))
    # Add recommendations for 'also downloaded' resources
    context['also_downloaded'] = \
        _format_recommendations(get_download_recommendations(resource))
    # Add 'more from same' links
    if get_more_from_same_projects_qs(resource).count():
        context['search_rel_projects'] = '{}/repository/search?q={}:{}'.format(
            DJANGO_URL, MORE_FROM_SAME_PROJECTS,
            resource.storage_object.identifier)
    if get_more_from_same_creators_qs(resource).count():
        context['search_rel_creators'] = '{}/repository/search?q={}:{}'.format(
            DJANGO_URL, MORE_FROM_SAME_CREATORS,
            resource.storage_object.identifier)

    # Render and return template with the defined context.
    ctx = RequestContext(request)
    # context['processing_info'] = json.loads(json.dumps(dict_xml).replace("@", "").replace("#", ""))
    return render_to_response(template,
                              context, context_instance=ctx)


def tuple2dict(_tuple):
    '''
    Recursively converts a tuple into a dictionary for ease of use 
    in templates.
    '''
    _dict = {}
    count_dict = {}
    for item in _tuple:
        if isinstance(item, tuple) or isinstance(item, list):
            if isinstance(item[0], basestring):
                # Replace spaces by underscores for component names.
                if item[0].find(" "):
                    _key = item[0].replace(" ", "_").replace("/", "_")
                else:
                    _key = item[0]
                if _key in _dict:
                    # If a repeatable component is found, a customized 
                    # dictionary is added, since no duplicate key names
                    # are allowed. We keep a dictionary with counts and
                    # add a new entry in the original dictionary in the 
                    # form <component>_<no_of_occurences>
                    if not _key in count_dict:
                        count_dict[_key] = 1
                    else:
                        count_dict[_key] += 1
                    new_key = "_".join([_key, str(count_dict[_key])])
                    _dict[new_key] = tuple2dict(item[1])
                else:
                    _dict[_key] = tuple2dict(item[1])
            else:
                if isinstance(item[0], tuple):
                    # Replace spaces by underscores for element names.
                    if item[0][0].find(" "):
                        _key = item[0][0].replace(" ", "_").replace('(', "").replace(")", "").replace("/", "_").replace(
                            "-", "_")
                    else:
                        _key = item[0][0]

                    # If the item is a date, convert it to real datetime
                    if _key.find("_date") != -1:
                        new_item = datetime.datetime.strptime(item[0][1], "%Y-%m-%d")
                    else:
                        new_item = item[0][1]
                    # If a repeatable element is found, the old value is
                    # concatenated with the new one, adding a space in between.
                    if _key in _dict:
                        _dict[_key] = ", ".join([_dict[_key], new_item])
                    else:
                        _dict[_key] = new_item
    return _dict


def _format_recommendations(recommended_resources):
    '''
    Returns the given resource recommendations list formatted as a list of
    dictionaries with the two keys "name" and "url" (for use in the single
    resource view).
    
    The number of returned recommendations is restricted to at most 4.
    '''
    result = []
    for res in recommended_resources[:4]:
        res_item = {}
        res_item['name'] = res.__unicode__()
        res_item['url'] = res.get_absolute_url()
        result.append(res_item)
    return result


class MetashareFacetedSearchView(FacetedSearchView):
    """
    A modified `FacetedSearchView` which makes sure that only such results will
    be returned that are accessible by the current user.
    """

    def get_results(self):
        sqs = super(MetashareFacetedSearchView, self).get_results()

        if not is_member(self.request.user, 'ecmembers') \
                and not is_member(self.request.user, 'elrcReviewers') \
                and not self.request.user.is_superuser:
            sqs = sqs.filter_and(publicationStatusFilter__exact='published')

        # Sort the results (on only one sorting value)
        if 'sort' in self.request.GET:
            sort_list = self.request.GET.getlist('sort')

            if sort_list[0] == 'resourcename_asc':
                sqs = sqs.order_by('resourceNameSort_exact')
            elif sort_list[0] == 'resourcename_desc':
                sqs = sqs.order_by('-resourceNameSort_exact')
            elif sort_list[0] == 'resourcetype_asc':
                sqs = sqs.order_by('resourceTypeSort_exact')
            elif sort_list[0] == 'resourcetype_desc':
                sqs = sqs.order_by('-resourceTypeSort_exact')
            elif sort_list[0] == 'mediatype_asc':
                sqs = sqs.order_by('mediaTypeSort_exact')
            elif sort_list[0] == 'mediatype_desc':
                sqs = sqs.order_by('-mediaTypeSort_exact')
            elif sort_list[0] == 'languagename_asc':
                sqs = sqs.order_by('languageNameSort_exact')
            elif sort_list[0] == 'languagename_desc':
                sqs = sqs.order_by('-languageNameSort_exact')
            elif sort_list[0] == 'dl_count_desc':
                sqs = sqs.order_by('-dl_count', 'resourceNameSort_exact')
            elif sort_list[0] == 'view_count_desc':
                sqs = sqs.order_by('-view_count', 'resourceNameSort_exact')
            else:
                sqs = sqs.order_by('resourceNameSort_exact')
        else:
            sqs = sqs.order_by('resourceNameSort_exact')

        # collect statistics about the query
        starttime = datetime.datetime.now()
        results_count = sqs.count()

        if self.query:
            saveQueryStats(self.query, \
                           str(sorted(self.request.GET.getlist("selected_facets"))), \
                           results_count, \
                           (datetime.datetime.now() - starttime).microseconds, self.request)
        return sqs

    def _get_selected_facets(self):
        """
        Returns the selected facets from the current GET request as a more
        structured Python dictionary.
        """
        result = {}
        for facet in self.request.GET.getlist("selected_facets"):
            if ":" in facet:
                field, value = facet.split(":", 1)
                if value:
                    if field in result:
                        result[field].append(value)
                    else:
                        result[field] = [value]
        return result

    def _create_filters_structure(self, facet_fields):
        """
        Creates a data structure encapsulating most of the logic which is
        required for rendering the filters/facets of the META-SHARE search.
        
        Takes the raw facet 'fields' dictionary which is (indirectly) returned
        by the `facet_counts()` method of a `SearchQuerySet`.
        """
        import re

        result = []
        # pylint: disable-msg=E1101
        filter_labels = [(name, field.label, field.facet_id, field.parent_id)
                         for name, field
                         in resourceInfoType_modelIndex.fields.iteritems()
                         if name.endswith("Filter")]
        filter_labels.sort(key=lambda f: f[2])
        sel_facets = self._get_selected_facets()
        # Step (1): if there are any selected facets, then add these first:
        if sel_facets:
            # add all top level facets (sorted by their facet IDs):
            for name, label, facet_id, _dummy in \
                    [f for f in filter_labels if f[3] == 0]:
                name_exact = '{0}_exact'.format(name)
                # only add selected facets in step (1)
                if name_exact in sel_facets:
                    items = facet_fields.get(name)
                    if items:
                        removable = []
                        addable = []
                        # only items with a count > 0 are shown
                        for item in [i for i in items if i[1] > 0]:
                            subfacets = [f for f in filter_labels if (f[3] == \
                                                                      facet_id and item[0] in f[0])]
                            subfacets_exactname_list = []
                            subfacets_exactname_list.extend( \
                                [u'{0}_exact'.format(subfacet[0]) \
                                 for subfacet in subfacets])
                            subresults = []
                            for facet in subfacets:
                                subresults = self.show_subfilter( \
                                    facet, sel_facets, facet_fields, subresults)
                            if item[0] in sel_facets[name_exact]:
                                if item[0] != "":
                                    lab_item = " ".join(re.findall( \
                                        '[A-Z\_]*[^A-Z]*', \
                                        item[0][0].capitalize() + item[0][1:]))[:-1]
                                    removable.append({'label': lab_item,
                                                      'count': item[1], 'targets':
                                                          [u'{0}:{1}'.format(name, value)
                                                           for name, values in
                                                           sel_facets.iteritems() for value in
                                                           values if (name != name_exact
                                                                      or value != item[0]) and name \
                                                           not in subfacets_exactname_list], \
                                                      'subresults': subresults})
                            else:
                                targets = [u'{0}:{1}'.format(name, value)
                                           for name, values in
                                           sel_facets.iteritems()
                                           for value in values]
                                targets.append(u'{0}:{1}'.format(name_exact,
                                                                 item[0]))
                                if item[0] != "":
                                    lab_item = " ".join(re.findall( \
                                        '[A-Z\_]*[^A-Z]*', \
                                        item[0][0].capitalize() + item[0][1:]))[:-1]
                                    addable.append({'label': lab_item,
                                                    'count': item[1],
                                                    'targets': targets,
                                                    'subresults': subresults})

                        result.append({'label': label, 'removable': removable,
                                       'addable': addable})

                        # Step (2): add all top level facets without selected facet items at the
        # end (sorted by their facet IDs):
        for name, label, facet_id, _dummy in \
                [f for f in filter_labels if f[3] == 0]:
            name_exact = '{0}_exact'.format(name)
            # only add facets without selected items in step (2)
            if not name_exact in sel_facets:
                items = facet_fields.get(name)
                if items:
                    addable = []
                    # only items with a count > 0 are shown
                    for item in [i for i in items if i[1] > 0]:
                        targets = [u'{0}:{1}'.format(name, value)
                                   for name, values in sel_facets.iteritems()
                                   for value in values]
                        targets.append(u'{0}:{1}'.format(name_exact, item[0]))

                        if item[0] != "":
                            lab_item = " ".join(re.findall('[A-Z\_]*[^A-Z]*',
                                                           item[0][0].capitalize() + item[0][1:]))[:-1]
                            addable.append({'label': lab_item, 'count': item[1],
                                            'targets': targets})
                    subresults = [f for f in filter_labels if f[3] == facet_id]
                    result.append({'label': label, 'removable': [],
                                   'addable': addable, 'subresults': subresults})

        return result

    def extra_context(self):
        extra = super(MetashareFacetedSearchView, self).extra_context()
        # add a data structure encapsulating most of the logic which is required
        # for rendering the filters/facets
        if 'fields' in extra['facets']:
            extra['filters'] = self._create_filters_structure(
                extra['facets']['fields'])
        else:
            # in case of forced empty search results, the fields entry is not set;
            # this can happen with recommendations when using the
            # get_more_from_same_... methods
            extra['filters'] = []
        return extra

    def show_subfilter(self, facet, sel_facets, facet_fields, results):
        """
        Creates a second level for faceting. 
        Sub filters are included after the parent filters.
        """
        import re

        name = facet[0]
        label = facet[1]

        name_exact = '{0}_exact'.format(name)

        if name_exact in sel_facets:
            items = facet_fields.get(name)
            if items:
                removable = []
                addable = []
                # only items with a count > 0 are shown
                for item in [i for i in items if i[1] > 0]:
                    if item[0] in sel_facets[name_exact]:
                        if item[0] != "":
                            lab_item = " ".join(re.findall('[A-Z\_]*[^A-Z]*',
                                                           item[0][0].capitalize() + item[0][1:]))[:-1]
                            removable.append({'label': lab_item,
                                              'count': item[1], 'targets':
                                                  [u'{0}:{1}'.format(name, value)
                                                   for name, values in
                                                   sel_facets.iteritems() for value in
                                                   values if name != name_exact
                                                   or value != item[0]]})
                    else:
                        targets = [u'{0}:{1}'.format(name, value)
                                   for name, values in
                                   sel_facets.iteritems()
                                   for value in values]
                        targets.append(u'{0}:{1}'.format(name_exact,
                                                         item[0]))
                        if item[0] != "":
                            lab_item = " ".join(re.findall('[A-Z\_]*[^A-Z]*',
                                                           item[0][0].capitalize() + item[0][1:]))[:-1]
                            addable.append({'label': lab_item,
                                            'count': item[1],
                                            'targets': targets})
                if (addable + removable):
                    results.append({'label': label, 'removable': removable,
                                    'addable': addable})
        else:
            items = facet_fields.get(name)
            if items:
                addable = []
                # only items with a count > 0 are shown
                for item in [i for i in items if i[1] > 0]:
                    targets = [u'{0}:{1}'.format(name, value)
                               for name, values in sel_facets.iteritems()
                               for value in values]
                    targets.append(u'{0}:{1}'.format(name_exact, item[0]))
                    if item[0] != "":
                        lab_item = " ".join(re.findall('[A-Z\_]*[^A-Z]*',
                                                       item[0][0].capitalize() + item[0][1:]))[:-1]
                        addable.append({'label': lab_item, 'count': item[1],
                                        'targets': targets})
                if addable:
                    results.append({'label': label, 'removable': [],
                                    'addable': addable})

        return results


@login_required
def contribute(request):
    tmp_dir = '{}/tmp'.format(CONTRIBUTION_FORM_DATA)  # temp dir for resources downloaded from user provided url
    if request.method == "POST":
        id = str(uuid.uuid4())
        profile = UserProfile.objects.get(user=request.user)
        data = {
            'userInfo': {
                'user': request.user.username,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
                'institution': profile.affiliation,
                'phoneNumber': profile.phone_number,
                'country': profile.country
            },

            'resourceInfo': {
                'resourceTitle': request.POST['resourceTitle'],
                'shortDescription': request.POST['shortDescription'],
            },
            'administration': {
                'processed': 'false',
                'edelivery': 'false'
            }
        }

        if 'languages[]' in request.POST:
            data['resourceInfo']['languages'] = request.POST.getlist('languages[]')

        if 'licence' in request.POST:
            data['resourceInfo']['licence'] = request.POST['licence']

        if 'other_info' in request.POST:
            data['resourceInfo']['other_info'] = request.POST['other_info']

        try:
            data['resourceInfo']['resourceUrl'] = request.POST['resourceUrl']
        except:
            pass

        dir1 = '{}/unprocessed'.format(CONTRIBUTION_FORM_DATA)
        # dir2 = '{}/{}'.format(dir1, id)

        import cgi

        form_data = cgi.FieldStorage()
        # file_data = form_data['filebutton'].value
        filename = '{}_{}'.format(profile.country, id)

        zipped = None
        # for chunk in request.FILES['filebutton'].chunks():
        #     destination.write(chunk)
        response = {}

        # if not request.POST['mode']:
        #     response['status'] = "failed"
        #     response['message'] = "Your request could not be completed. " \
        #                           "An unexpected error has occured. " \
        #                           "Please check your contribution mode and try again in a few minutes."
        #     return HttpResponse(json.dumps(response), mimetype="application/json")

        if request.POST['mode'] == 'uploadzip':
            zipped = filename + ".zip"
            if not request.FILES['filebutton'].size > MAXIMUM_UPLOAD_SIZE:
                try:
                    if not os.path.isdir(dir1):
                        os.makedirs(dir1)
                except:
                    raise OSError, "Could not write to CONTRIBUTION_FORM_DATA path"

                destination = open('{}/{}'.format(dir1, zipped), 'wb+')
                for chunk in request.FILES['filebutton'].chunks():
                    destination.write(chunk)
                destination.close()
                import zipfile
                zfile_path = '{}/{}'.format(dir1, zipped)
                zfile = zipfile.ZipFile(zfile_path)
                zip_ok = True
                try:
                    if zfile.testzip() is not None:
                        zip_ok = False
                except:
                    zip_ok = False
                if not zipfile.is_zipfile(zfile_path) or \
                        not zip_ok or \
                        not str(request.FILES['filebutton']).endswith(".zip"):
                    os.remove(zfile_path)
                    response['status'] = "failed"
                    response['message'] = "Your request could not be completed. " \
                                          "The file you tried to upload is corrupted or it is not a valid '.zip' file." \
                                          "Please make sure that you have compressed your data properly."
                    return HttpResponse(json.dumps(response), content_type="text/plain")

            else:
                response['status'] = "failed"
                response['message'] = "The file you are trying to upload " \
                                      "is larger than the maximum upload file size ({:.10} MB)!".format(
                    float(MAXIMUM_UPLOAD_SIZE) / (1024 * 1024))
                return HttpResponse(json.dumps(response), content_type="text/plain")

        data['administration']['resource_file'] = filename + '.xml'
        if zipped:
            data['administration']['dataset'] = {"zip": zipped}
        else:
            try:
                data['administration']['dataset'] = {"url": data['resourceInfo']['resourceUrl']}
            except KeyError:
                data['administration']['dataset'] = "None"
        if request.POST['mode'] == 'eDelivery':
            data['administration']['edelivery'] = 'true'
            del data['administration']
        # create the form data xml file
        xml = dicttoxml.dicttoxml(data, custom_root='resource', attr_type=False)
        xml_file = filename + ".xml"
        # download file if mode is "eDelivery"
        if request.POST['mode'] == 'eDelivery':
            try:
                response = HttpResponse(xml, content_type='text/xml')
                response['Content-Disposition'] = 'attachment; filename={}-contribution-info.xml'.format(request.user)
                return response
            except Exception:
                return HttpResponseNotFound(_('Could not generate eDelivery metadata XML'))

        xml_file_path = "{}/{}".format(dir1, xml_file)
        with open(xml_file_path, 'w') as f:
            xml_file = File(f)
            xml_file.write(xml)
            xml_file.closed
            f.closed
        try:
            send_mail("New unmanaged contributions",
                      "You have new unmanaged contributed resources on elrc-share.eu",
                      # 'no-reply@elrc-share.ilsp.gr', ["mdel@ilsp.gr"],
                      'no-reply@elrc-share.ilsp.gr', CONTRIBUTIONS_ALERT_EMAILS, \
                      # 'no-reply@elrc-share.ilsp.gr', ["mdel@ilsp.gr"], \
                      fail_silently=False)
        except:
            LOGGER.error("An error has occurred while trying to send email to contributions"
                         "alert recipients.")

        response['status'] = "succeded"
        response['message'] = "Thank you for sharing! Your data have been successfully submitted. " \
                              "You can now go on and contribute more data."
        # if request.POST['mode'] == 'uploadzip':
        return HttpResponse(json.dumps(response), content_type="text/plain")
        # else:
        #     return render_to_response('repository/editor/contributions/contribute.html', \
        #                               response, context_instance=RequestContext(request))

    return render_to_response('repository/editor/contributions/contribute.html', \
                              context_instance=RequestContext(request))


@user_passes_test(lambda u: u.is_superuser)
def manage_contributed_data(request):
    template = 'repository/editor/contributions/manage_contributed_data.html'
    xml_files = list()
    base = '{}/unprocessed'.format(CONTRIBUTION_FORM_DATA)
    for file in os.listdir(base):
        if file.endswith(".xml"):
            xml_files.append(file)

    info = list()
    for xml_file in xml_files:
        doc = etree.parse('{}/{}'.format(base, xml_file))
        dataset = {}
        if doc.xpath("//resource/administration/dataset/zip"):
            dataset = {
                "zip": doc.xpath("//resource/administration/dataset/zip/text()")
            }

        elif doc.xpath("//resource/administration/dataset/url"):
            dataset = {
                "url": doc.xpath("//resource/administration/dataset/url/text()")
            }

        info.append({
            "title": doc.xpath("//resourceTitle//text()"),
            "description": doc.xpath("//shortDescription//text()"),
            "languages": doc.xpath("//languages/item/text()"),
            "licence": doc.xpath("//licence/text()"),
            "other_info": doc.xpath("//other_info/text()"),
            "userInfo": {
                "firstname": doc.xpath("//userInfo/first_name/text()"),
                "lastname": doc.xpath("//userInfo/last_name/text()"),
                "country": doc.xpath("//userInfo/country/text()"),
                "phoneNumber": doc.xpath("//userInfo/phoneNumber/text()"),
                "email": doc.xpath("//userInfo/email/text()"),
                "user": doc.xpath("//userInfo/user/text()"),
                "institution": doc.xpath("//userInfo/institution/text()"),

            },
            "resource_file": doc.xpath("//resource/administration/resource_file/text()"),
            "dataset": dataset,
            'edelivery': util.strtobool(doc.xpath("//resource/administration/edelivery/text()")[0]),
            'msg_id': doc.xpath("//resource/administration/edelivery/@msg_id")

        })
    context = {
        'filelist': info
    }
    ctx = RequestContext(request)

    return render_to_response(template, context, context_instance=ctx)


@staff_member_required
def get_data(request, filename):
    dl_path = "{}/unprocessed/{}".format(CONTRIBUTION_FORM_DATA, filename)
    if dl_path:
        try:
            def dl_stream_generator():
                with open(dl_path, 'rb') as _local_data:
                    _chunk = _local_data.read(4096)
                    while _chunk:
                        yield _chunk
                        _chunk = _local_data.read(4096)

            # build HTTP response with a guessed mime type; the response
            # content is a stream of the download file
            filemimetype = guess_type(dl_path)[0] or "application/octet-stream"
            response = HttpResponse(dl_stream_generator(),
                                    content_type=filemimetype)
            response['Content-Length'] = getsize(dl_path)
            response['Content-Disposition'] = 'attachment; filename={0}' \
                .format(split(dl_path)[1])
            # LOGGER.info("Offering a local editor download of resource #{0}." \
            #             .format(object_id))
            return response
        except:
            pass


@staff_member_required
def remove(request, record):
    record = record.split(".xml")[0]
    path = "{}/unprocessed/{}".format(CONTRIBUTION_FORM_DATA, record)
    # if xml exists, flag it and move it to the processed
    if os.path.exists(path + ".xml"):
        xml_destination = '{}/processed/{}'.format(CONTRIBUTION_FORM_DATA,
                                                   "REMOVED_{}.xml".format(record))
        shutil.move(path + ".xml", xml_destination)
    if os.path.exists(path + ".zip"):
        xml_destination = '{}/processed/{}'.format(CONTRIBUTION_FORM_DATA,
                                                   "REMOVED_{}.zip".format(record))
        shutil.move(path + ".zip", xml_destination)
    return redirect(manage_contributed_data)


@user_passes_test(lambda u: u.is_superuser)
def addtodb(request):
    recipients = []
    total_res = 0
    # get the list of maintainers from the dat file
    maintainers = {}
    with open('{}/maintainers_test.dat'.format(CONTRIBUTION_FORM_DATA)) as f:
        for line in f:
            (key, val) = line.split(":")
            maintainers[key.strip()] = val.strip()
        f.close()
    # get the list all of files listed
    files = request.POST.getlist('file[]')

    # get the list of resource types
    types = request.POST.getlist('resourceType[]')

    # map the two list into a dictionary
    dictionary = dict(zip(files, types))

    # we will create descriptions only for those resources that have a
    # resource type specified
    valid = {}
    recipients_resources = {}
    contributor_resources = {}
    base = '{}/unprocessed'.format(CONTRIBUTION_FORM_DATA)
    for key, value in dictionary.items():
        if dictionary[key] != "":
            valid[key] = dictionary[key]
    for file, type in valid.iteritems():
        doc = etree.parse('{}/{}'.format(base, file))
        c_fname = ''.join(doc.xpath("//userInfo/first_name/text()"))
        c_lname = ''.join(doc.xpath("//userInfo/last_name/text()"))
        c_username = ''.join(doc.xpath("//userInfo/user/text()"))

        contributor = User.objects.get(first_name=c_fname,
                                       last_name=c_lname,
                                       username=c_username)
        contributor_name = "{} {}".format(contributor.first_name.encode('utf-8'),
                                          contributor.last_name.encode('utf-8'))
        contributor_email = contributor.email

        d = create_description(file, type, base, request.user)
        # d[0]: resource, d[1]:person, d[2]: country
        if not contributor_name in contributor_resources.keys():
            contributor_resources[contributor_name] = {"email": contributor_email, "resources": []}
        contributor_resources[contributor_name]["resources"].append(
            d[0].identificationInfo.resourceName['en']
        )
        # add the contributor to owners nevertheless
        d[0].owners.add(contributor.id)

        res_maintainers = maintainers[d[2]].split(",")
        users = []
        for rm in res_maintainers:
            rm_user = User.objects.get(username=rm)
            users.append(rm_user)
            d[0].owners.add(rm_user.id)
            d[0].contactPerson.add(d[1])
            info = "\nContact Details:\n" \
                   "First Name: {}\n" \
                   "Last Name: {}\n" \
                   "Email: {}\n" \
                   "Tel No: {}\n" \
                   "Organization: {}".format \
                (d[1].givenName, d[1].surname, d[1].communicationInfo.email,
                 d[1].communicationInfo.telephoneNumber, d[1].affiliation)

            if not rm_user.first_name + " " + rm_user.last_name in recipients:
                recipients.append(rm_user.first_name + " " + rm_user.last_name)

        if not recipients_resources.has_key(maintainers[d[2]]):
            recipients_resources[maintainers[d[2]]] = {"count": 1}
            recipients_resources[maintainers[d[2]]]["email"] = [rm.email for rm in users]
        else:
            recipients_resources[maintainers[d[2]]]["count"] += 1

        total_res += 1

    for recipient in recipients_resources.iterkeys():
        if recipients_resources[recipient]["count"] > 0:
            if recipients_resources[recipient]["count"] > 1:
                title = "{} new resources from contributors".format(recipients_resources[recipient]["count"])
                text = "You have received {} new resources from contributors. " \
                       "Please check your ELRC-SHARE repository account.".format(
                    recipients_resources[recipient]["count"])
            else:
                title = "1 new resource from contributors"
                text = "You have received 1 new resource from contributors. " \
                       "Please check your ELRC-SHARE repository account."

            try:
                send_mail(title, text, \
                          'no-reply@elrc-share.ilsp.gr', recipients_resources[recipient]["email"], fail_silently=False)
            except:
                if total_res > 1:
                    msg = '{} resources have been successfully imported into the database. '.format(total_res)
                else:
                    msg = '1 resource has been successfully imported into the database. '
                messages.error(request, msg + 'However, there was a problem sending email to the maintainers.')
                return redirect(manage_contributed_data)

    ### email to contributors
    for cr in contributor_resources:
        lr_list = ""
        mailto = contributor_resources[cr]['email']
        for lr in contributor_resources[cr]['resources']:
            lr_list += "\n\t" + str(contributor_resources[cr]['resources'].index(lr) + 1) + ". " + lr

        msg_to_contributor = "Dear {},\n\n" \
                             "Your resources" \
                             "{}\n" \
                             "have been imported into the ELRC-SHARE repository.\n" \
                             "An ELRC member will now further describe your resources, " \
                             "i.e. will complete the required metadata and review the " \
                             "licencing conditions. During this process, we may " \
                             "contact you for additional information. " \
                             "Please, note that the description of your contributed resources " \
                             "will be available for browsing and searching through the repository " \
                             "only when this process is completed.\n\n" \
                             "Thank you for sharing!\n\n" \
                             "The ELRC-SHARE team".format(cr, lr_list).decode('utf-8')

        try:
            send_mail("Your resources in the ELRC-SHARE repository", msg_to_contributor, \
                      'no-reply@elrc-share.ilsp.gr', [mailto], fail_silently=False)
        except:
            pass

    if total_res > 1:

        msg = u'{} resources have been successfully imported into ' \
              u'the database. ' \
              u'A notification email has been sent to the maintainers ({})'.format(total_res, u", ".join(recipients))
        messages.success(request, msg)
    elif total_res == 1:
        msg = u'1 resource has been successfully imported into ' \
              u'the database. ' \
              u'A notification email has been sent to ' \
              u'{}'.format(u", ".join(recipients))
        messages.success(request, msg)
    else:
        msg = u'No Resources Selected'
        messages.warning(request, msg)
    return redirect(manage_contributed_data)


def create_description(xml_file, type, base, user):
    # base = '{}/unprocessed'.format(WEB_FORM_STORAGE)
    doc = etree.parse('{}/{}'.format(base, xml_file))
    info = {
        "title": ''.join(doc.xpath("//resourceTitle//text()")),
        "description": ''.join(doc.xpath("//shortDescription//text()")),
        "languages": doc.xpath("//languages/item/text()"),
        "licence": doc.xpath("//licence/text()"),
        "userInfo": {
            "firstname": ''.join(doc.xpath("//userInfo/first_name/text()")),
            "lastname": ''.join(doc.xpath("//userInfo/last_name/text()")),
            "country": ''.join(doc.xpath("//userInfo/country/text()")),
            "phoneNumber": ''.join(doc.xpath("//userInfo/phoneNumber/text()")),
            "email": ''.join(doc.xpath("//userInfo/email/text()")),
            "user": ''.join(doc.xpath("//userInfo/user/text()")),
            "institution": ''.join(doc.xpath("//userInfo/institution/text()")),

        },
        "resource_file": ''.join(doc.xpath("//resource/administration/resource_file/text()")),
        "dataset": ''.join(doc.xpath("//resource/administration/dataset/zip/text()"))
    }
    # Create a new Identification object
    identification = identificationInfoType_model.objects.create( \
        resourceName={'en': info['title'].encode('utf-8')},
        description={'en': info['description'].encode('utf-8')}, )
    resource_creation = resourceCreationInfoType_model.objects.create(
        createdUsingELRCServices=False
    )

    # CONTACT PERSON:

    # COMMUNICATION
    email = info["userInfo"]["email"]
    if not communicationInfoType_model.objects.filter \
                (email=[email]).exists():
        communication = communicationInfoType_model.objects.create \
            (email=[email], country=info["userInfo"]["country"],
             telephoneNumber=[info["userInfo"]["phoneNumber"]])
    else:
        communication = communicationInfoType_model.objects.filter \
                            (email=[email])[:1][0]
    # ORGANIZATION
    if not organizationInfoType_model.objects.filter \
                (organizationName={'en': info["userInfo"]["institution"]},
                 communicationInfo=communication).exists():
        organization = organizationInfoType_model.objects.create \
            (organizationName={'en': info["userInfo"]["institution"]},
             communicationInfo=communicationInfoType_model.objects.create \
                 (email=[email], country=info["userInfo"]["country"], \
                  telephoneNumber=[info["userInfo"]["phoneNumber"]]))

    else:
        organization = organizationInfoType_model.objects.filter \
            (organizationName={'en': info["userInfo"]["institution"]},
             communicationInfo=communication)[0]

    # PERSON
    if not personInfoType_model.objects.filter \
                (surname={'en': info["userInfo"]["lastname"]},
                 givenName={'en': info["userInfo"]["firstname"]},
                 ).exists():
        cperson = personInfoType_model.objects.create \
            (surname={'en': info["userInfo"]["lastname"]},
             givenName={'en': info["userInfo"]["firstname"]},
             communicationInfo= \
                 communicationInfoType_model.objects.create \
                     (email=[email], country=info["userInfo"]["country"], \
                      telephoneNumber=[info["userInfo"]["phoneNumber"]]))
        cperson.affiliation.add(organization)

    else:
        cperson = personInfoType_model.objects.filter \
            (surname={'en': info["userInfo"]["lastname"]},
             givenName={'en': info["userInfo"]["firstname"]},
             )[0]
    resource = None

    # Handle different resource type structures
    if type == 'corpus':
        corpus_media_type = corpusMediaTypeType_model.objects.create()

        corpus_text = corpusTextInfoType_model.objects.create(mediaType='text',
                                                              back_to_corpusmediatypetype_model_id=corpus_media_type.id, \
                                                              lingualityInfo=lingualityInfoType_model.objects.create())

        # create language Infos
        if info['languages']:
            for lang in info['languages']:
                languageInfoType_model.objects.create(languageName=lang, \
                                                      back_to_corpustextinfotype_model=corpus_text)
        if len(info['languages']) == 1:
            corpus_text.lingualityInfo.lingualityType = u'monolingual'
            corpus_text.lingualityInfo.save()
        elif len(info['languages']) == 2:
            corpus_text.lingualityInfo.lingualityType = u'bilingual'
            corpus_text.lingualityInfo.save()
        elif len(info['languages']) > 2:
            corpus_text.lingualityInfo.lingualityType = u'multilingual'
            corpus_text.lingualityInfo.save()

        corpus_info = corpusInfoType_model.objects.create(corpusMediaType=corpus_media_type)

        resource = resourceInfoType_model.objects.create(identificationInfo=identification,
                                                         resourceComponentType=corpus_info,
                                                         metadataInfo=metadataInfoType_model.objects.create \
                                                             (metadataCreationDate=datetime.date.today(),
                                                              metadataLastDateUpdated=datetime.date.today()),
                                                         resourceCreationInfo=resource_creation)

    elif type == 'langdesc':
        langdesc_text = languageDescriptionTextInfoType_model.objects.create(mediaType='text',
                                                                             lingualityInfo=lingualityInfoType_model.objects.create())

        language_description_media_type = languageDescriptionMediaTypeType_model.objects.create(
            languageDescriptionTextInfo=langdesc_text)

        # create language Infos
        if info['languages']:
            for lang in info['languages']:
                languageInfoType_model.objects.create(languageName=lang, \
                                                      back_to_languagedescriptiontextinfotype_model=langdesc_text)

        if len(info['languages']) == 1:
            langdesc_text.lingualityInfo.lingualityType = u'monolingual'
            langdesc_text.lingualityInfo.save()
        elif len(info['languages']) == 2:
            langdesc_text.lingualityInfo.lingualityType = u'bilingual'
            langdesc_text.lingualityInfo.save()
        elif len(info['languages']) > 2:
            langdesc_text.lingualityInfo.lingualityType = u'multilingual'
            langdesc_text.lingualityInfo.save()

        langdesc_info = languageDescriptionInfoType_model.objects.create(
            languageDescriptionMediaType=language_description_media_type)

        resource = resourceInfoType_model.objects.create(identificationInfo=identification,
                                                         resourceComponentType=langdesc_info,
                                                         metadataInfo=metadataInfoType_model.objects.create \
                                                             (metadataCreationDate=datetime.date.today(),
                                                              metadataLastDateUpdated=datetime.date.today()))

    elif type == 'lexicon':
        lexicalConceptual_text = lexicalConceptualResourceTextInfoType_model.objects.create(mediaType='text',
                                                                                            lingualityInfo=lingualityInfoType_model.objects.create())
        lexicon_media_type = lexicalConceptualResourceMediaTypeType_model.objects.create(
            lexicalConceptualResourceTextInfo=lexicalConceptual_text)

        if info['languages']:
            for lang in info['languages']:
                languageInfoType_model.objects.create(languageName=lang, \
                                                      back_to_lexicalconceptualresourcetextinfotype_model=lexicalConceptual_text)

        if len(info['languages']) == 1:
            lexicalConceptual_text.lingualityInfo.lingualityType = u'monolingual'
            lexicalConceptual_text.lingualityInfo.save()
        elif len(info['languages']) == 2:
            lexicalConceptual_text.lingualityInfo.lingualityType = u'bilingual'
            lexicalConceptual_text.lingualityInfo.save()
        elif len(info['languages']) > 2:
            lexicalConceptual_text.lingualityInfo.lingualityType = u'multilingual'
            lexicalConceptual_text.lingualityInfo.save()

        lexicon_info = lexicalConceptualResourceInfoType_model.objects.create(
            lexicalConceptualResourceMediaType=lexicon_media_type)

        resource = resourceInfoType_model.objects.create(identificationInfo=identification,
                                                         resourceComponentType=lexicon_info,
                                                         metadataInfo=metadataInfoType_model.objects.create \
                                                             (metadataCreationDate=datetime.date.today(),
                                                              metadataLastDateUpdated=datetime.date.today()))
    # create distributionInfo object
    availability = u"underReview"
    psi = False
    licence = u"underReview"
    if info['licence']:
        availability = u'available'
        licence = info['licence'][0]
        if info['licence'] == u'openUnder-PSI':
            psi = True
    distribution = distributionInfoType_model.objects.create(
        availability=availability,
        PSI=psi)
    licence_obj = licenceInfoType_model.objects.create(licence=licence)
    distribution.licenceInfo.add(licence_obj)
    resource.distributioninfotype_model_set.add(distribution)
    resource.save()

    # also add the designated maintainer, based on the country of the country of the donor
    resource.owners.add(user.id)
    # finally move the dataset to the respective storage folder
    data_destination = resource.storage_object._storage_folder()
    try:
        if not os.path.isdir(data_destination):
            os.makedirs(data_destination)
    except:
        raise OSError, "STORAGE_PATH and LOCK_DIR must exist and be writable!"

    # finally, if the user has provided a zip file dataset,
    # move the dataset to the respective storage folder
    if info['dataset'] != '':
        data_source = '{}/{}'.format(base, info['dataset'])

        shutil.move(data_source, '{}/{}'.format(data_destination, "archive.zip"))
        resource.storage_object.compute_checksum()
        resource.storage_object.save()
        resource.storage_object.update_storage()

    # move the processed xml file to the web_form/processed folder
    xml_source = '{}/{}'.format(base, xml_file)
    processed_file = "{}_{}.xml".format(xml_file.split('_')[0], resource.id)
    xml_destination = '{}/processed/{}'.format(CONTRIBUTION_FORM_DATA, processed_file)
    shutil.move(xml_source, xml_destination)

    return (resource, cperson, info['userInfo']['country'])


status = {"p": "PUBLISHED", "g": "INGESTED", "i": "INTERNAL"}


def repo_report(request):
    '''
    Returns all resources in the repository as an excel file with
    predefined data to include.
    Get from url the 'email_to' variable
    '''
    email_to = request.GET.get('email_to', '')
    now = datetime.datetime.now()
    then = now - datetime.timedelta(days=15)
    resources = resourceInfoType_model.objects.filter(
        storage_object__deleted=False)
    link = None
    if len(resources) > 0:
        output = StringIO.StringIO()
        workbook = xlsxwriter.Workbook(output)

        ## formating
        heading = workbook.add_format(
            {'font_size': 11, 'font_color': 'white', 'bold': True, 'bg_color': "#058DBE", 'border': 1})
        bold = workbook.add_format({'bold': True})
        date_format = workbook.add_format({'num_format': 'yyyy, mmmm d'})
        title = "ELRC-SHARE_OVERVIEW_{}".format(
            datetime.datetime.now().strftime("%Y-%m-%d"))
        worksheet = workbook.add_worksheet(name=title)

        worksheet.write('A1', 'Resource ID', heading)
        worksheet.write('B1', 'Resource Name', heading)
        worksheet.write('C1', 'Type', heading)
        worksheet.write('D1', 'Mimetypes', heading)
        worksheet.write('E1', 'Linguality', heading)
        worksheet.write('F1', 'Language(s)', heading)
        worksheet.write_comment('F1', 'Delimited by "|" as per language')
        worksheet.write('G1', 'Resource Size', heading)
        worksheet.write_comment('G1', 'Delimited by "|" as per size')
        worksheet.write('H1', 'Resource Size Unit(s)', heading)
        worksheet.write('I1', 'Domain(s)', heading)
        worksheet.write('J1', 'DSI Relevance', heading)
        worksheet.write('K1', 'Legal Status', heading)
        worksheet.write('L1', 'PSI', heading)
        worksheet.write('M1', 'Countries', heading)
        worksheet.write('N1', 'Contacts', heading)
        worksheet.write('O1', 'Partner', heading)
        worksheet.write('P1', 'Project', heading)
        worksheet.write('Q1', 'Processed', heading)
        worksheet.write('R1', 'Related To', heading)
        worksheet.write('S1', 'Validated', heading)
        worksheet.write('T1', 'To be delivered to EC', heading)
        worksheet.write('U1', 'Delivered to EC', heading)
        worksheet.write('V1', 'Status', heading)
        worksheet.write('W1', 'Date', heading)
        worksheet.write('X1', 'Views', heading)
        worksheet.write('Y1', 'Downloads', heading)
        worksheet.write('Z1', 'Delivered to ODP', heading)
        worksheet.write('AA1', 'Unique', heading)

        link = True

        j = 1
        for i in range(len(resources)):

            res = resources[i]
            crawled = "YES" if res.resourceCreationInfo and res.resourceCreationInfo.createdUsingELRCServices else "NO"
            psi_list = [d.PSI for d in res.distributioninfotype_model_set.all()]
            psi = "YES" if any(psi_list) else "NO"

            country = _get_country(res)
            contacts = []
            licences = []
            try:
                for dist in res.distributioninfotype_model_set.all():
                    for licence_info in dist.licenceInfo.all():
                        licences.append(licence_info.licence)
            except:
                licences.append("underReview")

            for cp in res.contactPerson.all():
                for afl in cp.affiliation.all():
                    try:
                        org_name = afl.organizationName['en']
                    except KeyError:
                        org_name = afl.organizationName[afl.organizationName.keys()[0]]
                # country.append(cp.communicationInfo.country)

                # try to get first and last name otherwise get only last name which is mandatory
                try:
                    contacts.append(u"{} {} ({})".format(cp.surname.values()[0], cp.givenName.values()[0],
                                                         ", ".join(cp.communicationInfo.email)))
                except IndexError:
                    contacts.append(u"{} ({})".format(cp.surname.values()[0],
                                                      ", ".join(cp.communicationInfo.email)))
                    # data to be reported
                    # resource name
            try:
                res_name = smart_str(res.identificationInfo.resourceName['en'])
            except KeyError:
                res_name = smart_str(res.identificationInfo.resourceName[res.identificationInfo.resourceName.keys()[0]])

            # date
            date = datetime.datetime.strptime(unicode(res.storage_object.created).split(" ")[0], "%Y-%m-%d")

            # stats
            num_downloads = model_utils.get_lr_stat_action_count(res.storage_object.identifier, DOWNLOAD_STAT)
            num_views = model_utils.get_lr_stat_action_count(res.storage_object.identifier, VIEW_STAT)

            # A1
            worksheet.write(j, 0, res.id)
            # B1
            worksheet.write(j, 1, res_name.decode('utf-8'), bold)
            # C1
            worksheet.write(j, 2, res.resource_type())
            # D1
            mimetypes = _get_resource_mimetypes(res)
            if mimetypes:
                mim = []
                for d in mimetypes:
                    mim.append(d)
                worksheet.write(j, 3, " | ".join(mim))
            else:
                worksheet.write(j, 3, "N/A")
            # E1
            linguality = _get_resource_linguality(res)
            worksheet.write(j, 4, ", ".join(linguality))
            # F1
            lang_info = _get_resource_lang_info(res)
            size_info = _get_resource_sizes(res)
            langs = []
            lang_sizes = []
            for l in lang_info:
                langs.append(l)
                lang_sizes.extend(_get_resource_lang_sizes(res, l))
            worksheet.write(j, 5, " | ".join(langs))
            # G1, H1
            preferred_size = _get_preferred_size(res)
            if preferred_size:
                if float(preferred_size.size).is_integer():
                    size_num = int(preferred_size.size)
                else:
                    size_num = float(preferred_size.size)
                worksheet.write_number(j, 6, size_num)
                worksheet.write(j, 7, prettify_camel_case_string(preferred_size.sizeUnit))
            else:
                worksheet.write(j, 6, "")
                worksheet.write(j, 7, "")

            domain_info = _get_resource_domain_info(res)
            dsis = "N/A"
            if res.identificationInfo.appropriatenessForDSI:
                dsis = ", ".join(res.identificationInfo.appropriatenessForDSI)
            # I1
            if domain_info:
                domains = []
                for d in domain_info:
                    domains.append(d)
                worksheet.write(j, 8, " | ".join(domains))
            else:
                worksheet.write(j, 8, "N/A")
            # J1
            worksheet.write(j, 9, dsis)
            # K1
            worksheet.write(j, 10, ", ".join(licences))
            # L1
            worksheet.write(j, 11, psi)
            # M1
            if country:
                worksheet.write(j, 12, country)
            else:
                worksheet.write(j, 12, "N/A")
            # N1
            if contacts:
                worksheet.write(j, 13, " | ".join(contacts))
            else:
                worksheet.write(j, 13, "N/A")
            # O1
            partner = res.management_object.partner_responsible
            worksheet.write(j, 14, partner)
            # P1
            # Funding projects
            try:
                rc = res.resourceCreationInfo
                try:
                    funding_projects = [fp.projectShortName['en'] for fp in rc.fundingProject.all()]
                except KeyError:
                    funding_projects = [fp.projectName['en'] for fp in rc.fundingProject.all()]
            except AttributeError:
                funding_projects = []
            worksheet.write(j, 15, ", ".join(funding_projects))
            # Q1
            is_processed = "YES" if res.management_object.is_processed_version else "NO"
            worksheet.write(j, 16, is_processed)
            # R1
            # related_ids
            related_ids = ""
            if res.relationinfotype_model_set.all():
                related_ids = ", ".join(set([rel.relatedResource.targetResourceNameURI
                                             for rel in res.relationinfotype_model_set.all()]))
            worksheet.write(j, 17, related_ids)
            # S1
            validated = "YES" if res.storage_object.get_validation() else "NO"
            worksheet.write(j, 18, validated)
            # T1
            to_be_delivered = "" if not res.management_object.to_be_delivered_to_EC else res.management_object.to_be_delivered_to_EC
            worksheet.write(j, 19, to_be_delivered)
            # U1
            delivered = "" if not res.management_object.delivered_to_EC else res.management_object.delivered_to_EC
            worksheet.write(j, 20, delivered)
            # V1
            worksheet.write(j, 21, status[res.storage_object.publication_status])
            # W1
            worksheet.write_datetime(j, 22, date, date_format)
            worksheet.write(j, 23, num_views)
            worksheet.write(j, 24, num_downloads)
            try:
                odp = "YES" if res.management_object.delivered_odp else "NO"
            except ObjectDoesNotExist:
                odp = "NO"
            worksheet.write(j, 25, odp)
            is_unique = "YES" if (_is_processed(res) or _is_not_processed_or_related(res)) else "NO"
            worksheet.write(j, 26, is_unique)
            j += 1
            # worksheet.write(i + 1, 3, _get_resource_size_info(res))
        # worksheet.write(len(resources)+2, 3, "Total Resources", bold)
        # worksheet.write_number(len(resources)+3, 3, len(resources))
        worksheet.freeze_panes(1, 0)
        workbook.close()
    if link:
        if not email_to == u'true':
            output.seek(0)
            response = HttpResponse(output.read(),
                                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response['Content-Disposition'] = "attachment; filename={}.xlsx".format(title)
            return response
        # return HttpResponse(_get_resource_lang_info(res))
        else:
            rp = open('{}/report_recipients.dat'.format(TMP)).read().splitlines()

            msg_body = "Dear all,\n" \
                       "Please find attached an overview of the resources available in the ELRC-SHARE " \
                       "repository and their status today, {}.\n" \
                       "Best regards,\n\n" \
                       "The ELRC-SHARE group".format(datetime.datetime.now().strftime("%d, %b %Y"))
            msg = EmailMessage("[ELRC] ERLC-SHARE weekly report", msg_body,
                               from_email='elrc-share@ilsp.gr', bcc=rp)
            msg.attach("{}.xlsx".format(title), output.getvalue(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            msg.send()
            return HttpResponse("{}: Weekly repository report sent to: {}\n"
                                .format(datetime.datetime.now().strftime("%a, %d %b %Y"), ", ".join(rp)))
    else:
        return HttpResponse("No Language Resources published within the last two weeks\n")


@login_required
def report_extended(request):
    from metashare.repository_reports.extended_report import extended_report
    data = extended_report()
    response = HttpResponse(data['output'].read(),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = "attachment; filename={}.xlsx".format(data['title'])

    return response