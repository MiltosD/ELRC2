import logging

from xml.etree.ElementTree import fromstring
from zipfile import is_zipfile

from django import forms
from django.core.exceptions import ValidationError

from metashare.settings import LOG_HANDLER, MAXIMUM_UPLOAD_SIZE
from metashare.storage.models import ALLOWED_ARCHIVE_EXTENSIONS, ALLOWED_VALIDATION_EXTENSIONS, \
    ALLOWED_LEGAL_DOCUMENTATION_EXTENSIONS

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)



def _validate_resource_data(value):
    """
    Validates that the uploaded resource data is valid.
    """
    if value.size > MAXIMUM_UPLOAD_SIZE:
        raise ValidationError('The maximum upload file size is {:.0f} ' \
          'MB!'.format(float(MAXIMUM_UPLOAD_SIZE)/(1024*1024)))
    
    _valid_extension = False
    for _allowed_extension in ALLOWED_ARCHIVE_EXTENSIONS:
        if value.name.lower().endswith(_allowed_extension):
            _valid_extension = True
            break
    
    if not _valid_extension:
        raise ValidationError('Invalid upload file type. Valid file types ' \
          'are: {}'.format(ALLOWED_ARCHIVE_EXTENSIONS))
    
    return value


## VALIDATION REPORT
def _validate_validation_report(value):
    """
    Validates that the uploaded resource data is valid.
    """
    _valid_extension = False
    for _allowed_extension in ALLOWED_VALIDATION_EXTENSIONS:
        if value.name.lower().endswith(_allowed_extension):
            _valid_extension = True
            break

    if not _valid_extension:
        raise ValidationError('Invalid upload file type. Valid file types ' \
          'are: {}'.format(ALLOWED_VALIDATION_EXTENSIONS))

    return value

## LEGAL DOCUMENTATION
def _validate_legal_documentation(value):
    """
    Validates that the uploaded resource data is valid.
    """
    _valid_extension = False
    for _allowed_extension in ALLOWED_LEGAL_DOCUMENTATION_EXTENSIONS:
        if value.name.lower().endswith(_allowed_extension):
            _valid_extension = True
            break

    if not _valid_extension:
        raise ValidationError('Invalid upload file type. Valid file types ' \
          'are: {}'.format(ALLOWED_LEGAL_DOCUMENTATION_EXTENSIONS))

    return value


def _validate_resource_description(value):
    """
    Validates that the uploaded resource description is valid.
    """
    filename = value.name.lower()
    if filename.endswith('.xml'):
        _xml_raw = ''
        for _chunk in value.chunks():
            _xml_raw += _chunk
        
        try:
            _xml_tree = fromstring(_xml_raw)
        except Exception, _msg:
            raise ValidationError(_msg)

    elif filename.endswith('.zip'):
        valid = False
        try:
            valid = is_zipfile(value)
            value.seek(0)
        except:
            valid = False
        if not valid:
            raise ValidationError('File is not a zip file.') 
    else:
        raise ValidationError('Invalid upload file type. XML or ZIP file required.')
    
    
    # For the moment, we simply pass through the received value.  Later, we
    # could run an XML validation script here or perform other checks...
    return value


class StorageObjectUploadForm(forms.Form):
    """
    Form to upload resource data into a StorageObject instance.
    """
    resource = forms.FileField(label="Resource",
      help_text="You can upload resource data (<{:.0f} MB) using this " \
      "widget. Note that this will overwrite the current data!".format(
        float(MAXIMUM_UPLOAD_SIZE/(1024*1024))),
      validators=[_validate_resource_data])

    uploadTerms = forms.BooleanField(label="Upload Terms",
      help_text="By clicking this checkbox, you confirm that you have " \
      "cleared permissions for the file you intend to upload.")

class ResourceDescriptionUploadForm(forms.Form):
    """
    Form to upload a resource description into the Django database.
    """
    description = forms.FileField(label="Resource Description(s)",
      help_text="You can upload a new resource description in XML format, " \
      "or many resource descriptions in a ZIP file containing XML files. " \
      "Please make sure the XML files are Schema-valid before proceeding.",
      validators=[_validate_resource_description])

    uploadTerms = forms.BooleanField(label="Upload Terms",
      help_text="By clicking this checkbox, you confirm that you have " \
      "cleared permissions for the description(s) you intend to upload.")


## VALIDATION REPORT
class ValidationUploadForm(forms.Form):
    """
    Form to upload resource data into a StorageObject instance.
    """
    report = forms.FileField(label="Report",
      help_text="You can upload your validation report in" \
      " '.pdf' format using this widget. Note that this will overwrite the current report if it exists!",
      validators=[_validate_validation_report])

# LEGAL DOCUMENTATION
class LegalDocumetationUploadForm(forms.Form):
    """
    Form to upload resource data into a StorageObject instance.
    """
    legalDocumentation = forms.FileField(label="Legal Documentation",
      help_text="You can upload a .zip file containing any additional legal documentation"
      " using this widget. Note that this will overwrite the current legal "
                "documentation zip file, if it exists!",
      validators=[_validate_legal_documentation])

