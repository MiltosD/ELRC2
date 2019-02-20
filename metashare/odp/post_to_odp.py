import StringIO
import json
import logging
import os
import pprint

import requests
from ckanapi import RemoteCKAN

from metashare.odp.elrc_to_odp import create_metadata, create_package
from metashare.repository.decorators import _resource_is_downloadable
from metashare.settings import ODP_CKAN_USER_AGENT, LOG_HANDLER, ODP_API_KEY
from ckanapi.errors import NotFound
from metashare.repository.models import resourceInfoType_model

# Setup logging support.
from metashare.xml_utils import to_xml_string

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)

# remote api to access
opd_api = RemoteCKAN('https://data.europa.eu/euodp/data', user_agent=ODP_CKAN_USER_AGENT, apikey=ODP_API_KEY)

# The ids of the resources of the repository to be added or updated in ODP
# This is also going to be a list of resources selected in project_management admin
odp_resources = []

resources_actions = {
    "add": list(),
    "update": list(),
    "delete": list(),
}

# get those resources from the repository
resources = resourceInfoType_model.objects.filter(storage_object__deleted=False)

exclude = [370, 371, 372, 373]
for r in resources:
    if _resource_is_downloadable(r) \
            and not r.management_object.delivered_odp \
            and r.id not in exclude:
        odp_resources.append(r)

# for r in resources:
#     LOGGER.info("Creating ODP metadata for resource '{}', ID: {}.".format(r, r.id))
#     pprint.pprint(json.dumps(create_package(r)))


def build_actions_dict():
    for r in resources:
        package_id = "elrc_{}".format(r.id)
        try:
            resource = opd_api.action.package_show(id=package_id)
            LOGGER.info("Dataset {} found in ODP".format(package_id))
            try:
                if not resource['modified_date'] == r.metadataInfo.metadataLastDateUpdated.isoformat():
                    LOGGER.info("Dataset {} scheduled for update".format(package_id))
                    resources_actions['update'].append(r)
            except AttributeError:
                LOGGER.info("ELRC Resource {} does not have a last modification date. PASS..".format(r.id))

                # print type(resource)
        except NotFound:
            LOGGER.warn("Dataset {} not found in ODP. Scheduled for adding.".format(package_id))
            resources_actions['add'].append(r)
    pprint.pprint(resources_actions)


# time.sleep(2)
# x['title'] = x['title'].replace("(ELRC) ", "")
# print opd_api.action.package_show(id="elrc_305")
def post_resource(resource):
    # create package
    all_data = create_package(resource)
    print json.dumps(all_data['package'])
    # del all_data['package']['private']
    opd_api.call_action("package_create", data_dict=all_data['package'])


    # # create resource dataset (no upload)
    # # opd_api.action.resource_create(all_data['dataset'])
    # opd_api.call_action("resource_create", data_dict=all_data['dataset'])
    # print all_data['dataset']
    #
    # # create resource metadata description
    # LOGGER.info("Creating metadata for resource {}".format(resource.id))
    # pattern = "ELRC_resource_{}".format(resource.id)
    # xml_string = to_xml_string(resource.export_to_elementtree(),
    #                            encoding="utf-8").encode("utf-8")
    # LOGGER.info("Creating xml file")
    # md_filename = 'odp_temp/{}_md.xml'.format(pattern)
    # with open(md_filename, 'w') as f:
    #     f.write(xml_string)
    #
    # data = all_data['metadata']
    # data['upload'] = md_filename
    # print data
    # # opd_api.action.resource_create(data)
    # opd_api.call_action("resource_create", data_dict=data)
    # os.remove(md_filename)
    #
    # # create resource valrep
    # valrep_data = all_data['valrep']
    #
    # valrep_data['upload'] = resource.storage_object.get_validation()
    # opd_api.call_action("resource_create", data_dict=valrep_data)
    # print valrep_data

    # set delivered odp
    # resource.management_object.to_be_delivered_odp = True
    # resource.management_object.delivered_odp = True
    # resource.management_object.save()
