from metashare.bcp47 import iana
from metashare.odp.opd_settings import odp_template, language_authority_seed_url, LANGUAGES_TREE, XPATH_TEMPLATE, \
    EUROVOC, EUROVOC_XPATH
from metashare.repository.models import lexicalConceptualResourceInfoType_model, \
    corpusInfoType_model, languageDescriptionInfoType_model
from metashare.repository.views import _get_resource_lang_info, _get_resource_mimetypes
from metashare.settings import DJANGO_URL


def _get_resource_domain_info(resource):
    domain_level = []
    concepts = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            domains = corpus_info.domaininfotype_model_set.all()
            for d in domains:
                domain_level.append(d.domain)
                if d.subdomain:
                    concepts.append(d.subdomain)

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            domains = lcr_media_type.lexicalConceptualResourceTextInfo.domaininfotype_model_set.all()
            for d in domains:
                domain_level.append(d.domain)
                if d.subdomain:
                    concepts.append(d.subdomain)

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            domains = ld_media_type.languageDescriptionTextInfo.domaininfotype_model_set.all()
            domain_level.extend([d.domain for d in domains])
            for d in domains:
                domain_level.append(d.domain)
                if d.subdomain:
                    concepts.append(d.subdomain)
    domain_level = list(set(domain_level))
    domain_level.sort()
    concepts = list(set(concepts))
    concepts.sort()
    return {"domains": domain_level, "concepts": concepts}


def _get_domains_and_concepts_uris(resource):
    domains_and_concepts = _get_resource_domain_info(resource)
    domains_list = list()
    concepts_list = list()
    for domain in domains_and_concepts['domains']:
        uri = EUROVOC.find(EUROVOC_XPATH.format(domain)).text
        domains_list.append(
            {
                "display_name": uri,
                "title": uri,
                "type": "eurovoc_domain",
                "name": "eurovoc_domain_{}".format(uri.split("/")[-1])
            }
        )

    for concept in domains_and_concepts['concepts']:
        uri = EUROVOC.find(EUROVOC_XPATH.format(concept)).text
        concepts_list.append(uri)

    return {"domains": domains_list, "concepts": concepts_list}


def create_dataset(resource, package_name):
    """
    Returns a dictionary containing information on the dataset related to the given ELRC resource
    :param resource:
    :return: dataset dictionary
    """

    dataFormats = [df for df in _get_resource_mimetypes(resource)]
    dataset_dict = {
        "description": "Data archive containing files in the following formats: {}".format(", ".join(dataFormats)),
        "format": "application/zip",
        "package_id": package_name,
        "url": "{}{}".format(DJANGO_URL, resource.get_absolute_url()),
        "resource_type": "http://www.w3.org/TR/vocab-dcat#Download"
    }

    return dataset_dict


def create_metadata(package_name):
    """
    :param package_name:
    :return: metadata dictionary
    """
    md_dict = {
        "description": "Metadata description",
        "format": "application/xml",
        "package_id": package_name,
        "url": "http://data.europa.eu/euodp/en/data/dataset/{}/Metadata_description.xml".format(package_name),
        "resource_type": "http://data.europa.eu/euodp/kos/documentation-type/RelatedDocumentation"
    }

    return md_dict


def create_validation_report(package_name):
    """
    Creates a new ODP resources containing information about the dataset per se
    :return:
    """
    valrep_dict = {
        "description": "Validation report",
        "format": "application/pdf",
        "package_id": package_name,
        "url": "http://data.europa.eu/euodp/en/data/dataset/{}/Validation_report.pdf".format(package_name),
        "resource_type": "http://data.europa.eu/euodp/kos/documentation-type/RelatedDocumentation"
    }

    return valrep_dict


def create_package(resource):
    """
    Creates metadata for a new OPD package with required resources for a given ELRC resource
    :param resource:
    :return: Dictionary {package_info, metadata, dataset, validation_report}
    """
    resource_media = resource.resourceComponentType.as_subclass()

    package_info = odp_template.copy()

    package_info['metadata_created'] = resource.metadataInfo.metadataCreationDate.isoformat()
    try:
        package_info['modified_date'] = resource.metadataInfo.metadataLastDateUpdated.isoformat()
    except AttributeError:
        package_info['modified_date'] = package_info['metadata_created']

    # add ELRC Resource specific information
    package_info['name'] = "elrc_{}".format(resource.id)
    package_info['url'] = package_info['url'].format("elrc_{}".format(resource.id))
    package_info['description'] = package_info['description'].format(
        resource.identificationInfo.description['en'].replace('\r', '').replace('\n', '').replace('"', "'"))
    package_info['identifier'] = "ELRC_{}".format(resource.id)
    package_info['title'] = resource.real_unicode_()

    # if resource is terminological, add "terminology" eurovoc concept
    if isinstance(resource_media, lexicalConceptualResourceInfoType_model):
        package_info['concepts_eurovoc'].append("http://eurovoc.europa.eu/4441")

    # add eurovocs
    for domain in _get_domains_and_concepts_uris(resource)['domains']:
        package_info['groups'].append(domain)
    for concept in _get_domains_and_concepts_uris(resource)['concepts']:
        package_info['concepts_eurovoc'].append(concept)

    package_info['language'] = [
        "{}{}".format(language_authority_seed_url,
                      LANGUAGES_TREE.find(XPATH_TEMPLATE.format(iana.get_language_subtag(lang))).text) for lang in
        _get_resource_lang_info(resource)]
    # Get the proper language code
    metadata_language = LANGUAGES_TREE.find(XPATH_TEMPLATE.format(resource.metadataInfo.metadataLanguageId[0])).text
    package_info['metadata_language'] = "{}{}".format(language_authority_seed_url, metadata_language)

    metadata = create_metadata(package_info['name'])
    dataset = create_dataset(resource, package_info['name'])
    validation_report = create_validation_report(package_info['name'])

    result = {'package': package_info, 'metadata': metadata, 'dataset': dataset, 'valrep': validation_report}
    package_info = None
    return result
