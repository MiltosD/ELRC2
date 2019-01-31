# coding=utf-8
from collections import OrderedDict

from datetime import datetime

from metashare.repository.dataformat_choices import MIMETYPEVALUE_TO_MIMETYPELABEL
from metashare.repository.models import resourceInfoType_model as rm, corpusInfoType_model, \
    lexicalConceptualResourceInfoType_model, languageDescriptionInfoType_model, toolServiceInfoType_model
from metashare.utils import prettify_camel_case_string
from data import all_countries, lang_dict, all_domains, types, excel_matrix
import pprint
import xlsxwriter

pp = pprint.PrettyPrinter(indent=4)


def get_resources():
    all_resources = rm.objects.filter(storage_object__deleted=False)
    resources = []
    # get only published or ingested processed resources
    for r in all_resources:
        is_relations = [rel.relationType.startswith("is") for rel in r.relationinfotype_model_set.all()]
        status = r.storage_object.publication_status
        if status == 'p' or (status == 'g' and any(is_relations)):
            resources.append(r)
    return resources


all_dsi = {
    u'OnlineDisputeResolution': 0, u'Europeana': 0, u'OpenDataPortal': 0, u'eJustice': 0,
    u'ElectronicExchangeOfSocialSecurityInformation': 0, u'saferInternet': 0,
    u'Cybersecurity': 0, u'eHealth': 0, u'eProcurement': 0,
    u'BusinessRegistersInterconnectionSystem': 0,
}

result_dict = {
    "countries": dict(),
    "languages": dict()
}

for c in all_countries:
    result_dict["countries"][c] = dict(total=0,
                                       types=OrderedDict(types.copy()),
                                       domains=all_domains.copy(),
                                       dsis=all_dsi.copy(),
                                       openess=0,
                                       )
result_dict["languages"] = lang_dict


def process(end=None):
    objects = get_resources()
    print len(objects)
    if end:
        e = datetime.strptime(end, "%Y-%m-%d")
        objects = [res for res in objects if res.storage_object.created <= e]
        print len(objects)
    for res in objects:
        type_info = _get_media_type(res)
        langs = set(_get_resource_lang_info(res))
        domains = set(_get_resource_domain_info(res))
        dsis = set(res.identificationInfo.appropriatenessForDSI)
        r_type = "{} {}".format(type_info[1], type_info[2])
        country = get_country(res)
        if country:
            result_dict["countries"][country]['total'] += 1
            try:
                result_dict["countries"][country]["types"][r_type] += 1
            except KeyError:
                result_dict["countries"][country]["types"][r_type] = 1

            for d in domains:
                if d:
                    try:
                        result_dict["countries"][country]["domains"][d] += 1
                    except KeyError:
                        result_dict["countries"][country]["domains"][d] = 1
            for dsi in dsis:
                try:
                    result_dict["countries"][country]["dsis"][dsi] += 1
                except KeyError:
                    result_dict["countries"][country]["dsis"][dsi] = 1
        for lang in langs:
            try:
                result_dict["languages"][lang][r_type] += 1
            except KeyError:
                result_dict["languages"][lang][r_type] = 1
    make_excel(result_dict, "ELRC-SHARE_[]_[]")


# TRY TO MAKE A COMPLEX EXCEL FILE

# data = process("2017-01-01", "2017-01-30")


def next_col(ccol):
    return chr(ord(ccol) + 1)


def make_excel(data, filename):
    workbook = xlsxwriter.Workbook('{}.xlsx'.format(filename))  # Change path
    wb_format_light_grey = workbook.add_format({'font_size': 11, 'bold': True,
                                                'bg_color': "#f2f2f2"})
    wb_format_light_grey.set_bottom(2)
    wb_format_light_grey.set_bottom_color("#ffffff")
    # --------------
    wb_format_light_grey_center = workbook.add_format({'font_size': 11, 'bold': True,
                                                       'bg_color': "#f2f2f2", 'align': "center"})
    wb_format_light_grey_center.set_bottom(2)
    wb_format_light_grey_center.set_bottom_color("#ffffff")
    # --------------
    wb_format_dark_grey = workbook.add_format({'font_size': 12, 'bold': True, 'font_color': 'white',
                                               'bg_color': "#808080"})
    wb_format_dark_grey.set_bottom(2)
    wb_format_dark_grey.set_right(2)
    wb_format_dark_grey.set_bottom_color("#ffffff")
    wb_format_dark_grey.set_right_color("#ffffff")

    ws_countries = workbook.add_worksheet("COUNTRIES")
    ws_countries_types = workbook.add_worksheet("COUNTRIES-TYPES")
    ws_countries_domains = workbook.add_worksheet("COUNTRIES-DOMAINS")
    ws_countries_dsis = workbook.add_worksheet("COUNTRIES-DSIs")
    ws_countries_openess = workbook.add_worksheet("COUNTRIES-OPENESS")

    # WS_COUNTRIES

    # set backgrounds col1 row3-32
    i = 3
    for country in sorted(data["countries"].keys()):
        ws_countries.write("A{}".format(i), country, wb_format_light_grey)
        ws_countries_types.write("A{}".format(i), country, wb_format_light_grey)
        ws_countries_domains.write("A{}".format(i), country, wb_format_light_grey)
        ws_countries_dsis.write("A{}".format(i), country, wb_format_light_grey)
        ws_countries_openess.write("A{}".format(i), country, wb_format_light_grey)
        i += 1
    ws_countries.write("A{}".format(i), "Grand Total", wb_format_dark_grey)
    ws_countries.write("B{}".format(i), "=SUM(B3:B32)", wb_format_dark_grey)
    ws_countries.write("B1", "", wb_format_dark_grey)
    ws_countries.write("B2", " #language resources", wb_format_dark_grey)
    ws_countries.write("A{}".format(i), "Grand Total", wb_format_dark_grey)
    # add the values
    i = 3
    for country in sorted(data["countries"].keys()):
        ws_countries.write("A{}".format(i), country, wb_format_light_grey)
        ws_countries.write("B{}".format(i), data["countries"][country]["total"], wb_format_dark_grey)
        i += 1

    # WS_COUNTRIES_TYPES
    ws_countries_types.merge_range('B1:H1', 'Type of Language Resource', wb_format_light_grey_center)
    ws_countries_types.write("A{}".format(i), "Totals per type", wb_format_dark_grey)
    for i in range(ord("B"), ord("I")):
        ws_countries_types.write("{}{}".format(chr(i), 33), "=SUM({}3:{}32)".format(chr(i), chr(i)),
                                 wb_format_dark_grey)
        i += 1

    col = "B"
    for r_type in types.keys():
        ws_countries_types.write("{}2".format(col), r_type, wb_format_light_grey)
        col = next_col(col)

    ws_countries_types.write("I1", "", wb_format_dark_grey)
    ws_countries_types.write("I2", "Totals per country", wb_format_dark_grey)
    for i in range(3, 34):
        ws_countries_types.write("I{}".format(i), "=SUM(B{}:H{})".format(i, i), wb_format_dark_grey)

    # add values
    for country in data["countries"].keys():
        for type in data["countries"][country]["types"].keys():
            ws_countries_types.write(excel_matrix["country_row"][country],
                                     excel_matrix["type_col"][type], data["countries"][country]["types"][type])
    # WS_COUNTRIES_DOMAINS
    ws_countries_domains.merge_range('B1:V1', 'EUROVOC DOMAIN', wb_format_light_grey_center)
    ws_countries_domains.write("W2", "Totals", wb_format_dark_grey)
    ws_countries_domains.write("A33", "Totals per domain", wb_format_dark_grey)
    for i in range(ord("B"), ord("W")):
        ws_countries_domains.write("{}{}".format(chr(i), 33), "=SUM({}3:{}32)".format(chr(i), chr(i)),
                                   wb_format_dark_grey)
        i += 1
    for i in range(3, 33):
        ws_countries_domains.write("W{}".format(i), "=SUM(B{}:V{})".format(i, i), wb_format_dark_grey)

    col = 'B'
    for d in OrderedDict(all_domains).keys():
        ws_countries_domains.write("{}2".format(col), d, wb_format_light_grey)
        col = next_col(col)
    # add values
    for country in data["countries"].keys():
        for dom in data["countries"][country]["domains"].keys():
            if dom != u"Other":
                ws_countries_domains.write(excel_matrix["country_row"][country],
                                           excel_matrix["domain_col"][dom], data["countries"][country]["domains"][dom])

    # WS_COUNTRIES_DSIs
    ws_countries_dsis.merge_range('B1:L1', 'Relevance to Sector Specific DSIs', wb_format_light_grey_center)
    ws_countries_dsis.write("L2", "Totals", wb_format_dark_grey)
    ws_countries_dsis.write("A33", "Totals per DSI", wb_format_dark_grey)
    for i in range(ord("B"), ord("L")):
        ws_countries_dsis.write("{}{}".format(chr(i), 33), "=SUM({}3:{}32)".format(chr(i), chr(i)),
                                wb_format_dark_grey)
        i += 1
    for i in range(3, 33):
        ws_countries_dsis.write("L{}".format(i), "=SUM(B{}:K{})".format(i, i), wb_format_dark_grey)

    col = 'B'
    for d in OrderedDict(all_dsi).keys():
        ws_countries_dsis.write("{}2".format(col), d, wb_format_light_grey)
        col = next_col(col)
    # add values
    for country in data["countries"].keys():
        for dsi in data["countries"][country]["dsis"].keys():
            ws_countries_dsis.write(excel_matrix["country_row"][country],
                                    excel_matrix["dsi_col"][dsi], data["countries"][country]["dsis"][dsi])

    workbook.close()


def _is_processed(r):
    relations = [relation.relationType for relation in r.relationinfotype_model_set.all() if
                 relation.relationType.startswith('is')]
    if (len(relations) > 1 and u"isPartOf" in relations) or len(relations) == 1:
        return True
    return False


def _is_not_processed_or_related(r):
    related_ids = set()
    if r.relationinfotype_model_set.all():
        related_ids = set([rel.relatedResource.targetResourceNameURI for rel in r.relationinfotype_model_set.all()])
    if related_ids:
        return False
    return True


def get_licenses(obj):
    """
    Returns a list of license under which the given language resource is
    available.
    """
    result = []
    for dist in obj.distributioninfotype_model_set.all():
        for licence_info in dist.licenceInfo.all():
            result.append(licence_info.licence)
    return result


def _get_preferred_size(resource):
    units = [u'translationUnits', u'sentences', u'segments', u'entries', u'terms', u'concepts', u'words', u'tokens']
    size_infos = _get_resource_size_infos(resource)
    for unit in units:
        preferred_unit = next((size_info for size_info in size_infos if size_info.sizeUnit == unit), None)
        if preferred_unit:
            return preferred_unit
        else:
            try:
                return size_infos[0]
            except IndexError:
                return None


def _get_country(res):
    res_countries = []
    for cp in res.contactPerson.all():
        res_countries.append(cp.communicationInfo.country)
        # now try to get the correct coutry
    if len(set(res_countries)) > 1 and res_countries[1]:
        res_country = res_countries[1]
    else:
        try:
            res_country = res_countries[0]
        except IndexError:
            return ""
    return res_country


def _get_resource_linguality(resource):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            result.append(corpus_info.lingualityInfo.lingualityType.title())

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            result.append(lcr_media_type \
                          .lexicalConceptualResourceTextInfo.lingualityInfo.lingualityType.title())

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.append(ld_media_type \
                          .languageDescriptionTextInfo.lingualityInfo.lingualityType.title())
    result = list(set(result))
    result.sort()
    return result


def _get_resource_lang_sizes(resource, language):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            for lang in corpus_info.languageinfotype_model_set.all():
                l = []
                if lang.languageName == language:
                    if _get_lang_sizes(lang):
                        l = [" - ".join(_get_lang_sizes(lang))]
                    else:
                        l = ["N/A"]
                result.extend(l)

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            for lang in lcr_media_type \
                    .lexicalConceptualResourceTextInfo.languageinfotype_model_set.all():
                l = []
                if lang.languageName == language:
                    if _get_lang_sizes(lang):
                        l = [" - ".join(_get_lang_sizes(lang))]
                    else:
                        l = ["N/A"]
                result.extend(l)

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            for lang in ld_media_type \
                    .languageDescriptionTextInfo.languageinfotype_model_set.all():
                l = []
                if lang.languageName == language:
                    if _get_lang_sizes(lang):
                        l = [" - ".join(_get_lang_sizes(lang))]
                    else:
                        l = ["N/A"]
                result.extend(l)
    result = list(set(result))
    result.sort()
    return result


def _get_lang_sizes(lang):
    return ['{:,}'.format(int(sp.size)) + " " + prettify_camel_case_string(sp.sizeUnit) for sp in
            lang.sizePerLanguage.all()]


def _get_resource_mimetypes(resource):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            result.extend([MIMETYPEVALUE_TO_MIMETYPELABEL.get(d.dataFormat) for d in
                           corpus_info.textformatinfotype_model_set.all()])

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        result.extend([MIMETYPEVALUE_TO_MIMETYPELABEL.get(d.dataFormat) for d in lcr_media_type \
                      .lexicalConceptualResourceTextInfo.textformatinfotype_model_set.all()])

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.extend([MIMETYPEVALUE_TO_MIMETYPELABEL.get(d.dataFormat) for d in ld_media_type \
                          .languageDescriptionTextInfo.textformatinfotype_model_set.all()])
    result = list(set(result))
    result.sort()

    return result


def _get_resource_sizes(resource):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            try:
                result.extend(
                    ["{}".format('{:,}'.format(int(s.size) if float(s.size).is_integer() else float(s.size))) for s in
                     corpus_info.sizeinfotype_model_set.all()])
            except ValueError:
                print ValueError.message, resource

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            result.extend(["{}".format('{:,}'.format(int(s.size) if float(s.size).is_integer() else float(s.size)))
                           for s in lcr_media_type \
                          .lexicalConceptualResourceTextInfo.sizeinfotype_model_set.all()])

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.extend(["{}".format('{:,}'.format(int(s.size) if float(s.size).is_integer() else float(s.size)))
                           for s in ld_media_type \
                          .languageDescriptionTextInfo.sizeinfotype_model_set.all()])
    result = list(set(result))
    result.sort()
    return result


def _get_resource_size_infos(resource):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            result.extend([s for s in corpus_info.sizeinfotype_model_set.all()])

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            result.extend([s for s in lcr_media_type \
                          .lexicalConceptualResourceTextInfo.sizeinfotype_model_set.all()])
    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.extend([s for s in ld_media_type \
                          .languageDescriptionTextInfo.sizeinfotype_model_set.all()])
    return result


def _get_resource_size_units(resource, size):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            for s in corpus_info.sizeinfotype_model_set.all():
                this_size = "{}".format('{:,}'.format(int(s.size) if float(s.size).is_integer() else float(s.size)))
                if this_size == size:
                    result.extend(["{}".format(prettify_camel_case_string(s.sizeUnit))])

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            for s in lcr_media_type \
                    .lexicalConceptualResourceTextInfo.sizeinfotype_model_set.all():
                this_size = "{}".format('{:,}'.format(int(s.size) if float(s.size).is_integer() else float(s.size)))
                if this_size == size:
                    result.extend(["{}".format(prettify_camel_case_string(s.sizeUnit))])

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            for s in ld_media_type \
                    .languageDescriptionTextInfo.sizeinfotype_model_set.all():
                this_size = "{}".format('{:,}'.format(int(s.size) if float(s.size).is_integer() else float(s.size)))
                if this_size == size:
                    result.extend(["{}".format(prettify_camel_case_string(s.sizeUnit))])
    result = list(set(result))
    result.sort()

    return result


def count_by_domain():
    domains = ["BUSINESS & COMPETITION", "INTERNATIONAL RELATIONS", "EDUCATION & COMMUNICATIONS",
               "PRODUCTION, TECHNOLOGY & RESEARCH", "LAW", "POLITICS", "EMPLOYMENT & WORKING CONDITIONS",
               "EUROPEAN UNION", "SOCIAL QUESTIONS", "FINANCE", "TRANSPORT", "ECONOMICS", "INDUSTRY",
               "AGRICULTURE, FORESTRY & FISHERIES", "GEOGRAPHY", "Other", "SCIENCE", "TRADE", "ENVIRONMENT",
               "AGRI-FOODSTUFFS", "INTERNATIONAL ORGANISATIONS", "ENERGY"]
    result = []
    for d in domains:
        count = 0
        for res in get_resources():
            if d in _get_resource_domain_info(res):
                count += 1
        result.append((d, count))
    return result


def _get_resource_domain_info(resource):
    result = []
    media = resource.resourceComponentType.as_subclass()

    if isinstance(media, corpusInfoType_model):
        media_type = media.corpusMediaType
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            result.extend([prettify_camel_case_string(d.domain)
                           if d.subdomain else prettify_camel_case_string(d.domain) for d in
                           corpus_info.domaininfotype_model_set.all()])

    elif isinstance(media, lexicalConceptualResourceInfoType_model):
        lcr_media_type = media.lexicalConceptualResourceMediaType
        if lcr_media_type.lexicalConceptualResourceTextInfo:
            result.extend([prettify_camel_case_string(d.domain)
                           if d.subdomain else prettify_camel_case_string(d.domain) for d in lcr_media_type \
                          .lexicalConceptualResourceTextInfo.domaininfotype_model_set.all()])

    elif isinstance(media, languageDescriptionInfoType_model):
        ld_media_type = media.languageDescriptionMediaType
        if ld_media_type.languageDescriptionTextInfo:
            result.extend([prettify_camel_case_string(d.domain)
                           if d.subdomain else prettify_camel_case_string(d.domain) for d in ld_media_type \
                          .languageDescriptionTextInfo.domaininfotype_model_set.all()])
    result = list(set(result))
    result.sort()

    return result


def _get_media_type(resource):
    linguality = []
    lr_type = None
    corpus_media = resource.resourceComponentType.as_subclass()
    if isinstance(corpus_media, corpusInfoType_model):
        media_type = corpus_media.corpusMediaType
        lr_type = "Corpus"
        for corpus_info in media_type.corpustextinfotype_model_set.all():
            linguality.append(corpus_info.lingualityInfo.lingualityType.title())
    elif isinstance(corpus_media, lexicalConceptualResourceInfoType_model):
        media_type = corpus_media.lexicalConceptualResourceMediaType
        lr_type = "Lexical"
        if media_type.lexicalConceptualResourceTextInfo:
            linguality.append(media_type.lexicalConceptualResourceTextInfo.
                              lingualityInfo.lingualityType.title())
    elif isinstance(corpus_media, languageDescriptionInfoType_model):
        media_type = corpus_media.languageDescriptionMediaType
        lr_type = "Language Description"
        if media_type.languageDescriptionTextInfo:
            linguality.append("Monolingual")
    elif isinstance(corpus_media, toolServiceInfoType_model):
        pass

    return media_type, lr_type, linguality[0]


def _get_resource_lang_info(resource):
    """
    Collect the data to filter the resources on Language Name
    """
    result = []
    corpus_media = resource.resourceComponentType.as_subclass()
    linguality = []
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
        pass

    return result


def get_country(res):
    res_countries = []
    for cp in res.contactPerson.all():
        res_countries.append(cp.communicationInfo.country)
        # now try to get the correct coutry
    if len(set(res_countries)) > 1 and res_countries[1]:
        res_country = res_countries[1]
    else:
        res_country = res_countries[0]
    return res_country
