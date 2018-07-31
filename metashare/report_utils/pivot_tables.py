# coding=utf-8
import StringIO
import datetime
import json
from smtplib import SMTPException

import xlsxwriter
from dateutil.relativedelta import relativedelta
from django.core.mail import EmailMessage
from django.http import HttpResponse
from metashare.settings import ILSP_ADMINS, UNIQUE_RESOURCES_SNAPSHOTS, TMP
from metashare.report_utils.extract_db_snapshot import create_snapshot
from metashare.report_utils.report_utils import _is_processed, _is_not_processed_or_related, get_licenses, \
    _get_resource_lang_info, _get_resource_domain_info, _get_resource_linguality
from metashare.repository.models import resourceInfoType_model

domains = {u"BUSINESS & COMPETITION": [0, 0, 0], u"INTERNATIONAL RELATIONS": [0, 0, 0],
           u"EDUCATION & COMMUNICATIONS": [0, 0, 0],
           u"PRODUCTION, TECHNOLOGY & RESEARCH": [0, 0, 0], u"LAW": [0, 0, 0], u"POLITICS": [0, 0, 0],
           u"EMPLOYMENT & WORKING CONDITIONS": [0, 0, 0],
           u"EUROPEAN UNION": [0, 0, 0], u"SOCIAL QUESTIONS": [0, 0, 0], u"FINANCE": [0, 0, 0], u"TRANSPORT": [0, 0, 0],
           u"ECONOMICS": [0, 0, 0],
           u"INDUSTRY": [0, 0, 0],
           u"AGRICULTURE, FORESTRY & FISHERIES": [0, 0, 0], u"GEOGRAPHY": [0, 0, 0], u"SCIENCE": [0, 0, 0],
           u"TRADE": [0, 0, 0],
           u"ENVIRONMENT": [0, 0, 0], u"AGRI-FOODSTUFFS": [0, 0, 0], u"INTERNATIONAL ORGANISATIONS": [0, 0, 0],
           u"ENERGY": [0, 0, 0], u"Other": [0, 0, 0]}

languages = {
    u"Bulgarian": [0, 0, 0], u"Czech": [0, 0, 0], u"Croatian": [0, 0, 0], u"Danish": [0, 0, 0],
    u"Dutch; Flemish": [0, 0, 0],
    u"English": [0, 0, 0],
    u"Estonian": [0, 0, 0], u"Finnish": [0, 0, 0], u"French": [0, 0, 0], u"German": [0, 0, 0], u"Hungarian": [0, 0, 0],
    u"Icelandic": [0, 0, 0], u"Irish": [0, 0, 0],
    u"Italian": [0, 0, 0], u"Latvian": [0, 0, 0],
    u"Lithuanian": [0, 0, 0], u"Maltese": [0, 0, 0], u"Modern Greek (1453-)": [0, 0, 0], u"Norwegian": [0, 0, 0],
    u"Norwegian Bokmål": [0, 0, 0],
    u"Norwegian Nynorsk": [0, 0, 0],
    u"Polish": [0, 0, 0], u"Portuguese": [0, 0, 0],
    u"Romanian; Moldavian; Moldovan": [0, 0, 0], u"Slovak": [0, 0, 0], u"Slovenian": [0, 0, 0],
    u"Spanish; Castilian": [0, 0, 0],
    u"Swedish": [0, 0, 0]
}

licences = {
    u'CC0-1.0': [0, 0, 0], u'CC-BY-4.0': [0, 0, 0], u'CC-BY-NC-4.0': [0, 0, 0], u'CC-BY-NC-ND-4.0': [0, 0, 0],
    u'CC-BY-NC-SA-4.0': [0, 0, 0],
    u'CC-BY-ND-4.0': [0, 0, 0], u'CC-BY-SA-4.0': [0, 0, 0], u'ODbL-1.0': [0, 0, 0], u'ODC-BY-1.0': [0, 0, 0],
    u'OGL-3.0': [0, 0, 0],
    u'PDDL-1.0': [0, 0, 0],
    u'openUnder-PSI': [0, 0, 0], u'CC-BY-3.0': [0, 0, 0], u'CC-BY-NC-3.0': [0, 0, 0], u'CC-BY-NC-ND-3.0': [0, 0, 0],
    u'CC-BY-NC-SA-3.0': [0, 0, 0],
    u'CC-BY-ND-3.0': [0, 0, 0], u'CC-BY-SA-3.0': [0, 0, 0], u'CC-BY-SA-2.5_Sl': [0, 0, 0],
    u'dl-de/by-2-0': [0, 0, 0], u'dl-de/zero-2-0': [0, 0, 0],
    u'IODL-1.0': [0, 0, 0], u'LO-OL-v2': [0, 0, 0],
    u'NCGL-1.0': [0, 0, 0], u'NLOD-1.0': [0, 0, 0], u'AGPL-3.0': [0, 0, 0], u'Apache-2.0': [0, 0, 0],
    u'BSD-4-Clause': [0, 0, 0],
    u'BSD-3-Clause': [0, 0, 0],
    u'BSD-2-Clause': [0, 0, 0], u'EPL-1.0': [0, 0, 0], u'GFDL-1.3': [0, 0, 0], u'GPL-2.0': [0, 0, 0],
    u'GPL-3.0': [0, 0, 0], u'LGPL-2.1': [0, 0, 0], u'LGPL-3.0': [0, 0, 0], u'EUPL-1.0': [0, 0, 0], u'EUPL-1.1': [0, 0, 0],
    u'EUPL-1.2': [0, 0, 0], u'MIT': [0, 0, 0], u'publicDomain': [0, 0, 0],
    u'underReview': [0, 0, 0], u'non-standard/Other_Licence/Terms': [0, 0, 0]}

dsis = {
    u'OnlineDisputeResolution': ["Online Dispute Resolution", 0, 0, 0],
    u'Europeana': ["Europeana", 0, 0, 0],
    u'OpenDataPortal': ["Open Data Portal", 0, 0, 0],
    u'eJustice': ["eJustice", 0, 0, 0],
    u'ElectronicExchangeOfSocialSecurityInformation': ["Electronic Exchange of Social Security Information", 0, 0, 0],
    u'saferInternet': ["Safer Internet", 0, 0, 0],
    u'Cybersecurity': ["Cyber Security", 0, 0, 0],
    u'eHealth': ["eHealth", 0, 0, 0],
    u'eProcurement': ["eProcurement", 0, 0, 0],
    u'BusinessRegistersInterconnectionSystem': ["Business Registers Interconnection System", 0, 0, 0],
}

lr_types = {
    u"Monolingual Corpus": [0, 0, 0],
    u"Bi-Multilingual Corpus": [0, 0, 0],
    u"Lexical resource": [0, 0, 0],
    u"Language description": [0, 0, 0],
}


def get_timespan(date1=None, date2=None):
    if date1 and date2:
        return date2 - datetime.timedelta(days=(date2 - date1).days)
    elif date2 and not date1:
        return date2
    else:
        return datetime.datetime.today() - relativedelta(months=1)


def _get_lr_type(resource):
    if resource['resourceType'] == "Corpus":
        if "Monolingual" in resource['linguality']:
            return u"Monolingual Corpus"
        else:
            return u"Bi-Multilingual Corpus"
    elif resource['resourceType'] == "Lexical conceptual resource":
        return u"Lexical resource"
    elif resource['resourceType'] == "Language description":
        return u"Language description"


def get_stats_dict(date1=None, date2=None):
    aggregate = {
        "info": {
            "timespan": {
                "low": None,
                "upper": None,
            }
        },
        "lr_types": lr_types,
        "languages": languages,
        "domains": domains,
        "licences": licences,
        "dsis": dsis
    }

    # 30 days back
    timespan = get_timespan(date1, date2)
    # assuming that this script will run on the 1st day of every month, we get the previous month
    today = datetime.date.today()
    previous_month = today - relativedelta(months=1)
    previous_month_data_file = "unique_resources_{}-{}-{}.json".format(
        previous_month.strftime('%d'),
        previous_month.strftime('%m'),
        previous_month.strftime('%Y'),
    )
    # return previous_month_data_file
    # get unique resources
    # unique_resources = [r for r in resourceInfoType_model.objects.filter(
    #     storage_object__deleted=False) if (_is_processed(r) or _is_not_processed_or_related(r))]

    unique_resources = json.load(open(create_snapshot()))

    previous_unique_resources = json.load(open('{}/{}'.format(UNIQUE_RESOURCES_SNAPSHOTS, previous_month_data_file)))

    try:
        aggregate['info']['timespan']['low'] = timespan.strftime("%d-%m-%yyyy")
        aggregate['info']['timespan']['upper'] = datetime.datetime.today().strftime("%d-%m-%yyyy")
    except AttributeError:
        aggregate['info']['timespan']['low'] = \
            (datetime.datetime.today() - datetime.timedelta(days=30)). \
                strftime("%d-%m-%yyyy")
        aggregate['info']['timespan']['upper'] = datetime.datetime.today().strftime("%d-%m-%yyyy")

    for resource in previous_unique_resources['unique_resources']['metadata']:
        try:
            lr_type = _get_lr_type(resource)
            lang_list = set(resource['languages'])
            licence_list = set(resource['licences'])
            domain_list = set(resource['domains'])
            dsi_list = resource['dsis']

            aggregate["lr_types"][lr_type][0] += 1

            for lang in lang_list:
                try:
                    aggregate['languages'][lang][0] += 1
                except KeyError:
                    # just ignore non eu languages
                    pass
            for licence in licence_list:
                aggregate['licences'][licence][0] += 1
            for domain in domain_list:
                aggregate['domains'][domain][0] += 1
            for dsi in dsi_list:
                aggregate['dsis'][dsi][1] += 1
        except KeyError:
            # The resource is a tool/service and we don't count it
            pass

    for resource in unique_resources['unique_resources']['metadata']:
        try:
            lr_type = _get_lr_type(resource)
            lang_list = set(resource['languages'])
            licence_list = set(resource['licences'])
            domain_list = set(resource['domains'])
            dsi_list = resource['dsis']

            aggregate["lr_types"][lr_type][1] += 1
            aggregate["lr_types"][lr_type][2] = aggregate["lr_types"][lr_type][1] - aggregate["lr_types"][lr_type][0]
            # populate languages count
            for lang in lang_list:
                try:
                    aggregate['languages'][lang][1] += 1
                    aggregate['languages'][lang][2] = aggregate['languages'][lang][1] - aggregate['languages'][lang][0]
                except KeyError:
                    # just ignore non eu languages
                    pass

            for licence in licence_list:
                aggregate['licences'][licence][1] += 1
                aggregate['licences'][licence][2] = aggregate['licences'][licence][1] - aggregate['licences'][licence][0]

            for domain in domain_list:
                aggregate['domains'][domain][1] += 1
                aggregate['domains'][domain][2] = aggregate['domains'][domain][1] - aggregate['domains'][domain][0]

            for dsi in dsi_list:
                aggregate['dsis'][dsi][2] += 1
                aggregate['dsis'][dsi][3] = aggregate['dsis'][dsi][2] - aggregate['dsis'][dsi][1]
        except KeyError:
            # The resource is a tool/service and we don't count it
            pass
    return aggregate


def create_pivot_report():
    data = get_stats_dict()
    # from metashare.repository_reports.pivot import d
    # data = d
    timespan = get_timespan()
    output = StringIO.StringIO()
    workbook = xlsxwriter.Workbook(output)
    # workbook = xlsxwriter.Workbook()
    heading = workbook.add_format(
        {'font_size': 11, 'font_color': 'white', 'bold': True, 'bg_color': "#058DBE", 'border': 1})
    bold = workbook.add_format({'bold': True})

    def _write_worksheet(key, name, offset):
        ws = workbook.add_worksheet(name=name)
        ws.write('B1', timespan.strftime("%d, %b %Y"), heading)
        ws.write('C1', datetime.datetime.today().strftime("%d, %b %Y"), heading)
        ws.write('D1', 'DIFF', heading)

        row = 1

        for k, v in sorted(data[key].iteritems()):
            if offset == 1:
                ws.write(row, 0, v[0])
            else:
                ws.write(row, 0, k)
            ws.write(row, 1, v[offset + 0])
            ws.write(row, 2, v[offset + 1])
            ws.write(row, 3, v[offset + 2])

            row += 1

    # LR Types
    _write_worksheet('lr_types', 'LR TYPES', 0)
    # Languages
    _write_worksheet('languages', 'CEF LANGUAGES', 0)
    # Licences
    _write_worksheet('licences', 'LICENCES', 0)
    # Domains
    _write_worksheet('domains', 'DOMAINS', 0)
    # Domains
    _write_worksheet('dsis', 'DSIs', 1)

    workbook.close()
    # Send email
    rp = open('{}/report_recipients.dat'.format(TMP)).read().splitlines()
    msg_body = "Dear all,\n" \
               "Please find attached the monthly progress report on the total number of " \
               "unique LRs hosted on ELRC-SHARE on {}.\n" \
               "Kind regards,\n\n" \
               "The ELRC-SHARE team".format(datetime.datetime.now().strftime("%d, %b %Y"))
    msg = EmailMessage("[ELRC] ELRC-SHARE monthly progress report", msg_body,
                       from_email='elrc-share@ilsp.gr', bcc=rp)
    # msg = EmailMessage("[ELRC] ELRC-SHARE monthly progress report", msg_body,
    #                    from_email='elrc-share@ilsp.gr', bcc=ILSP_ADMINS)
    msg.attach("ELRC-SHARE_monthly_progress_{}.xlsx".format(datetime.datetime.now().strftime("%Y-%m-%d")),
               output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    try:
        msg.send()
    except SMTPException as e:
        print('There was an error sending an email: ', e)
    return HttpResponse("{}: CEF Digital repository report sent to: {}\n"
                        .format(datetime.datetime.now().strftime("%a, %d %b %Y"), ", ".join(rp)))
