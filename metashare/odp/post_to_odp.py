import logging
import pprint
from ckanapi import RemoteCKAN
from metashare.settings import ODP_CKAN_USER_AGENT, LOG_HANDLER, ODP_API_KEY
from ckanapi.errors import NotFound
from metashare.repository.models import resourceInfoType_model

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)

# remote api to access
odp_api = RemoteCKAN('https://data.europa.eu/euodp/data', user_agent=ODP_CKAN_USER_AGENT, apikey=ODP_API_KEY)

# The ids of the resources of the repository to be added or updated in ODP
# This is also going to be a list of resources selected in project_management admin
odp_resources = []

resources_actions = {
    "add": list(),
    "update": list(),
    "delete": list(),
}

# get those resources from the repository
resources = resourceInfoType_model.objects.filter(id__in=odp_resources)


# for r in resources:
#     LOGGER.info("Creating ODP metadata for resource '{}', ID: {}.".format(r, r.id))
#     pprint.pprint(json.dumps(create_package(r)))
def build_actions_dict():
    for r in resources:
        package_id = "elrc_{}".format(r.id)
        try:
            resource = odp_api.action.package_show(id=package_id)
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
    return resources_actions

