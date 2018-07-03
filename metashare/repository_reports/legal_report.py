import StringIO
import datetime

import xlsxwriter
from django.core.exceptions import ObjectDoesNotExist
from django.utils.encoding import smart_str
from metashare.report_utils.report_utils import _is_processed, _is_not_processed_or_related
from metashare.repository import model_utils
from metashare.repository.fields import best_lang_value_retriever
from metashare.repository.models import resourceInfoType_model, organizationInfoType_model
from metashare.repository.views import _get_resource_lang_info, _get_resource_sizes, _get_resource_lang_sizes, \
    _get_preferred_size, _get_resource_domain_info, status, _get_country, _get_resource_mimetypes, \
    _get_resource_linguality
from metashare.stats.model_utils import DOWNLOAD_STAT, VIEW_STAT
from metashare.utils import prettify_camel_case_string


def extended_report():
    '''
    Returns all resources in the repository as an excel file with
    predefined data to include.
    Get from url the 'email_to' variable
    '''
    now = datetime.datetime.now()
    then = now - datetime.timedelta(days=15)
    resources = resourceInfoType_model.objects.filter(
        storage_object__deleted=False)
    link = None
    if len(resources) > 0:
        title = "ELRC-SHARE_{}-EXT".format(
            datetime.datetime.now().strftime("%d-%m-%y"))
        output = StringIO.StringIO()
        workbook = xlsxwriter.Workbook(output)

        ## formating
        heading = workbook.add_format(
            {'font_size': 11, 'font_color': 'white', 'bold': True, 'bg_color': "#058DBE", 'border': 1})
        bold = workbook.add_format({'bold': True})
        date_format = workbook.add_format({'num_format': 'yyyy, mmmm d'})
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

        worksheet.write('AA1', 'Personal Data', heading)
        worksheet.write('AB1', 'Sensitive Data', heading)
        worksheet.write('AC1', 'Other Licence Name', heading)
        worksheet.write('AD1', 'Other Licence Terms Text', heading)
        worksheet.write('AE1', 'Other Licence Terms URL', heading)
        worksheet.write('AF1', 'Conditions of Use', heading)
        worksheet.write('AG1', 'IPR Holder', heading)
        worksheet.write('AH1', 'Legal Documentation', heading)
        worksheet.write('AI1', 'Allows Uses Besides DGT', heading)
        worksheet.write('AJ1', 'IPR Clearing Status', heading)
        worksheet.write('AK1', 'IPR Comments', heading)
        worksheet.write('AL1', 'Unique', heading)
        # worksheet.write('AM1', 'Unique', heading)

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

            personal_data = "YES" if True in set(
                [d.personalDataIncluded for d in res.distributioninfotype_model_set.all()]) else "NO"
            worksheet.write(j, 26, personal_data)

            sensitive_data = "YES" if True in set(
                [d.sensitiveDataIncluded for d in res.distributioninfotype_model_set.all()]) else "NO"
            worksheet.write(j, 27, sensitive_data)

            other_licences = []
            for dist in res.distributioninfotype_model_set.all():
                for licence_info in dist.licenceInfo.all():
                    other_licences.append(licence_info.otherLicenceName)

            try:
                worksheet.write(j, 28, ", ".join(other_licences))
            except TypeError:
                pass

            other_licences_text = []
            for dist in res.distributioninfotype_model_set.all():
                for licence_info in dist.licenceInfo.all():
                    other_licences_text.append(best_lang_value_retriever(licence_info.otherLicence_TermsText))

            worksheet.write(j, 29, ", ".join(other_licences_text))

            other_licences_url = []
            for dist in res.distributioninfotype_model_set.all():
                for licence_info in dist.licenceInfo.all():
                    other_licences_url.append(licence_info.otherLicence_TermsURL)

            worksheet.write(j, 30, ", ".join(other_licences_url))

            restrictions = []
            for dist in res.distributioninfotype_model_set.all():
                for licence_info in dist.licenceInfo.all():
                    restrictions.extend(licence_info.restrictionsOfUse)

            worksheet.write(j, 31, ", ".join(restrictions))

            ipr_holders = []
            for dist in res.distributioninfotype_model_set.all():
                for ip in dist.iprHolder.all():
                    subclass = ip.as_subclass()
                    if isinstance(ip.as_subclass(), organizationInfoType_model):
                        ipr_holders.append(
                            u"{} ({})".format(best_lang_value_retriever(subclass.organizationName).encode('utf-8'),
                                              ", ".join(subclass.communicationInfo.email)))
                    else:
                        ipr_holders.append(
                            u"{} {} ({})".format(best_lang_value_retriever(subclass.givenName).encode('utf-8'),
                                                 best_lang_value_retriever(subclass.surname).encode('utf-8'),
                                                 ", ".join(subclass.communicationInfo.email)))
            worksheet.write(j, 32, u", ".join(ipr_holders))

            worksheet.write(j, 33, "YES" if res.storage_object.get_legal_documentation() else "NO")

            dgt = "YES" if True in set(
                [d.allowsUsesBesidesDGT for d in res.distributioninfotype_model_set.all()]) else "NO"
            ipr_status = prettify_camel_case_string(res.management_object.ipr_clearing) if \
                res.management_object.ipr_clearing else ""
            worksheet.write(j, 34, dgt)
            worksheet.write(j, 35, ipr_status)
            ipr_comments = res.management_object.comments
            worksheet.write(j, 36, ipr_comments)
            # resource_description = best_lang_value_retriever(res.identificationInfo.description)
            # worksheet.write(j, 37, resource_description)
            is_unique = "YES" if (_is_processed(res) or _is_not_processed_or_related(res)) else "NO"

            worksheet.write(j, 37, is_unique)
            j += 1
            # worksheet.write(i + 1, 3, _get_resource_size_info(res))
        # worksheet.write(len(resources)+2, 3, "Total Resources", bold)
        # worksheet.write_number(len(resources)+3, 3, len(resources))
        worksheet.freeze_panes(1, 0)
        workbook.close()

        output.seek(0)
        return {"output": output, "title": title}
