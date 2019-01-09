from django.db import models
from metashare.settings import PARTNERS
from metashare.repository.models import resourceInfoType_model
from metashare.repository.supermodel import _make_choices_from_list

DELIVERABLES = _make_choices_from_list(
    ["CEF-ELRC", "ELRC Network",
     "ELRC Data D2.1", "ELRC Data D2.2",
     "ELRC Data D2.3", "ELRC Data D2.4",
     "ELRC Data D3.1", "ELRC Data D3.2",
     "ELRC Data D3.3", "ELRC Data D3.3.1",
     "ELRC Data D3.3.2", "ELRC Data D3.4"
     "ELRC Data D3.4.1", "ELRC Data D3.4.2"
     ]
)

IPR_CLEARING = _make_choices_from_list(
    ["underClearing", "cleared", "notClearable"]
)

country_to_partner_map = {
    "Austria": "DFKI", "Belgium": "ELDA", "Bulgaria": "ILSP", "Croatia": "ILSP", "Cyprus": "ILSP",
    "Czech Republic": "DFKI", "Denmark": "TILDE", "Estonia": "TILDE", "Finland": "TILDE", "France": "ELDA",
    "Germany": "DFKI", "Greece": "ILSP", "Hungary": "DFKI", "Iceland": "TILDE", "Ireland": "ELDA", "Italy": "ELDA",
    "Latvia": "TILDE", "Lithuania": "TILDE", "Luxembourg": "DFKI", "Malta": "ELDA", "Netherlands": "DFKI",
    "Norway": "TILDE",
    "Poland": "ILSP", "Portugal": "ELDA", "Romania": "ILSP", "Slovakia": "ILSP", "Slovenia": "ILSP", "Spain": "ELDA",
    "Sweden": "TILDE", "United Kingdom": "ELDA", None: ""
}

FUNDING_PROJECTS = [
    u'ELRC Data', u'CEF-ELRC', u'ELRC Network'
]


def _get_country(res):
    res_countries = []
    for cp in res.contactPerson.all():
        res_countries.append(cp.communicationInfo.country)
        # now try to get the correct coutry
    try:
        if len(set(res_countries)) > 1 and res_countries[1]:
            res_country = res_countries[1]
        else:
            res_country = res_countries[0]
    except IndexError:
        res_country = None
    return res_country


class ManagementObject(models.Model):
    resource = models.OneToOneField(resourceInfoType_model, blank=True, null=True, related_name="management_object")

    delivered_to_EC = models.CharField(
        verbose_name='Delivered to EC',
        choices=sorted(DELIVERABLES['choices']),
        max_length=20, blank=True, null=True)

    to_be_delivered_to_EC = models.CharField(
        verbose_name='To be delivered to EC',
        choices=sorted(DELIVERABLES['choices']),
        max_length=20, blank=True, null=True)

    is_processed_version = models.BooleanField(verbose_name="Is Processed Version", default=False, editable=False)

    validated = models.BooleanField(verbose_name="Validated", default=False, editable=False)

    partner_responsible = models.CharField(verbose_name="Partner", max_length=6,
                                           choices=_make_choices_from_list(PARTNERS)['choices'],
                                           editable=False,
                                           blank=True, null=True)

    rejected = models.BooleanField(verbose_name="Rejected from Processing", default=False)

    rejection_reason = models.TextField(max_length=1000, blank=True, null=True)

    # ODP
    to_be_delivered_odp = models.NullBooleanField(verbose_name="To be delivered to ODP", null=True, blank=True)
    delivered_odp = models.BooleanField(verbose_name="Delivered to ODP", default=False)

    ipr_clearing = models.CharField(verbose_name="IPR Clearing", max_length=13,
                                    choices=IPR_CLEARING['choices'],
                                    blank=True, null=True)

    comments = models.TextField(
        verbose_name="Comments",
        max_length=1000,
        blank=True,
        null=True)

    unique_together = ("rejected", "rejection_reason")

    def _set_is_processed_version(self):
        relations = [relation.relationType.startswith('is') for relation in
                     self.resource.relationinfotype_model_set.all()]
        self.is_processed_version = any(relations)

    def _set_validated(self):
        self.validated = True if self.resource.storage_object.get_validation() else False

    def _set_partner(self):
        resource_country = _get_country(self.resource)

        # Set partner only if LR funding project is valid (cf. FUNDING_PROJECTS)
        resource_funding_projects = []
        try:
            resource_funding_projects = \
                [p.projectShortName['en'] for p in self.resource.resourceCreationInfo.fundingProject.all()]
        except:
            pass
        # check if at least one of the resources's funding project is a FUNDING_PROJECT
        if set(FUNDING_PROJECTS).intersection(resource_funding_projects):
            self.partner_responsible = country_to_partner_map.get(resource_country)
        else:
            self.partner_responsible = None

    def __unicode__(self):
        _unicode = u'{} (id: "{}")'.format(self.resource, self.id)
        return _unicode

    def save(self, *args, **kwargs):
        self._set_is_processed_version()
        self._set_validated()
        self._set_partner()
        if not self.resource:
            self.resource = self.get_related_resource().__unicode__()
        if self.rejected and not self.rejection_reason:
            return
        elif not self.rejected and self.rejection_reason:
            self.rejection_reason = None
        super(ManagementObject, self).save(*args, **kwargs)
