import asyncio
import json
import logging
import os
import shlex
import re

import xml.etree.ElementTree as ET

from . import process_provider
from . import util
from .. import exception
from xml.dom import minidom

logger = logging.getLogger(__name__)


# TODO: NCL-3503: Finish implementation once the other components are figured out
def get_pme_provider(execution_name, pme_jar_path, pme_parameters, output_to_logs=False, specific_indy_group=None, timestamp=None):

    @asyncio.coroutine
    def get_result_data(work_dir, group_id=None, artifact_id=None):

        raw_result_data = "{}"
        result_file_path = work_dir + "/target/pom-manip-ext-result.json"

        if os.path.isfile(result_file_path):
            with open(result_file_path, "r") as file:
                raw_result_data = file.read()

        logger.info('Got PME result data "{raw_result_data}".'.format(**locals()))
        pme_result = json.loads(raw_result_data)

        if group_id is not None and artifact_id is not None:
            logger.warn("Overriding the groupId of the result to: " + group_id)
            pme_result['VersioningState']['executionRootModified']['groupId'] = group_id

            logger.warn("Overriding the artifactId of the result to: " + artifact_id)
            pme_result['VersioningState']['executionRootModified']['artifactId'] =  artifact_id

        try:
            pme_result["RemovedRepositories"] = util.get_removed_repos(work_dir, pme_parameters)
        except FileNotFoundError as e:
            logger.error('File for removed repositories could not be found')
            logger.error(str(e))

        return pme_result


    def is_pme_disabled_via_extra_parameters(extra_adjust_parameters):
        """
        Check if PME is disabled via one of the parameters passed to PME by the user

        return: :bool:
        """
        paramsString = extra_adjust_parameters.get("CUSTOM_PME_PARAMETERS", None)

        if paramsString is None:
            return False

        else:

            params = shlex.split(paramsString)

            for p in params:

                if p.startswith("-Dmanipulation.disable=true"):
                    return True
            else:
                return False

    @asyncio.coroutine
    def get_extra_param_execution_root_name(extra_adjust_parameters):
        """
        If the parameter 'EXECUTION_ROOT_NAME' is present, the string value should be in format '<group_id>:<artifact_id>'

        Return the group_id,artifact_id value.

        If the string is in the wrong format or if the parameter is not present, return None,None instead
        """
        paramsString = extra_adjust_parameters.get("EXECUTION_ROOT_NAME", None)

        if paramsString is None:
            return None, None
        else:
            result = paramsString.split(':')
            if len(result) == 2:
                return result[0], result[1]
            else:
                logger.warn('EXECUTION_ROOT_NAME parameter has as value the wrong format. It should be "<group_id>:<artifact_id>"')
                logger.warn('Value provided is: "' + paramsString + '"')
                return None, None

    @asyncio.coroutine
    def adjust(repo_dir, extra_adjust_parameters, adjust_result):
        nonlocal execution_name

        temp_build_parameters = []

        if timestamp:
            temp_build_parameters.append("-DversionIncrementalSuffix=" + timestamp + "-redhat")

        if specific_indy_group:
            temp_build_parameters.append("-DrestRepositoryGroup=" + specific_indy_group)

        extra_parameters, subfolder = yield from util.get_extra_parameters(extra_adjust_parameters)

        jvm_version = util.get_jvm_from_extra_parameters(extra_parameters)

        if jvm_version:
            location = '/usr/lib/jvm/java-' + jvm_version + '-openjdk/bin/'
            logger.info("Specifying java path: " + location)
        else:
            location = ''

        yield from util.print_java_version(java_bin_dir=location)

        # readjust the repo_dir to run PME from the folder where the root pom.xml is located
        # See: PRODTASKS-361
        repo_dir = os.path.join(repo_dir, subfolder)

        cmd = [location + "java", "-jar", pme_jar_path] \
              + pme_parameters + temp_build_parameters + extra_parameters

        logger.info('Executing "' + execution_name + '" using "pme" adjust provider '
                    + '(delegating to "process" provider). Command is "{cmd}".'.format(**locals()))

        res = yield from process_provider.get_process_provider(execution_name,
                                                     cmd,
                                                     get_result_data=get_result_data,
                                                     send_log=output_to_logs) \
            (repo_dir, extra_adjust_parameters, adjust_result)

        pme_disabled = is_pme_disabled_via_extra_parameters(extra_adjust_parameters)

        if pme_disabled:
            logger.warning("PME is disabled via extra parameters")
            yield from create_pme_result_file(repo_dir)

        override_group_id, override_artifact_id = yield from get_extra_param_execution_root_name(extra_adjust_parameters)

        adjust_result['resultData'] = yield from get_result_data(repo_dir, override_group_id, override_artifact_id)
        return res

    return adjust

@asyncio.coroutine
def get_version_from_pme_result(pme_result):
    """
    Format of pme_result should be as follows:

    {
      "VersioningState": {
        "executionRootModified": {
          "groupId": "<group-id>",
          "artifactId": "<artifact-id>",
          "version": "<pme'd version>"
        }
      }
    }

    Function tries to extract version generated by PME from the pme_result

    Parameters:
    - pme_result: :dict:
    """
    try:
        version = pme_result['VersioningState']['executionRootModified']['version']
        return version
    except  Exception as e:
        logger.error("Couldn't extract PME result version from JSON file")
        logger.error(e)
        return None


@asyncio.coroutine
def get_gav_from_pom(pom_xml_file):

    tree = ET.parse(pom_xml_file)
    root = tree.getroot()

    if '{' in root.tag and '}' in root.tag:
        namespace_search = '{{{}}}'.format(root.tag.split('}')[0].strip('{'))
    else:
        namespace_search = ''

    parent = root.find(namespace_search + 'parent')
    parent_group_id = None
    parent_version = None

    # https://maven.apache.org/pom.html#Maven_Coordinates
    # Docs concerning how inheritance of groupId and version from parent
    if parent is not None:


        parent_group_id_elem = parent.find(namespace_search + 'groupId')
        parent_version_elem = parent.find(namespace_search + 'version')

        if parent_group_id_elem is not None:
            parent_group_id = parent_group_id_elem.text

        if parent_version_elem is not None:
            parent_version = parent_version_elem.text

    group_id_elem = root.find(namespace_search + 'groupId')

    if group_id_elem is not None:
        group_id = group_id_elem.text

    elif (group_id_elem is None) and (parent_group_id is not None):
        logger.info("Using parent groupId information")
        group_id = parent_group_id

    else:
        raise Exception("Could not find the groupId in the pom.xml")

    artif_id_elem = root.find(namespace_search + 'artifactId')

    if artif_id_elem is not None:
        artif_id = artif_id_elem.text
    else:
        raise Exception("Could not find the artifactId in the pom.xml")

    version_elem  = root.find(namespace_search + 'version')

    if version_elem is not None:
        version = version_elem.text

    elif (version_elem is None) and (parent_version is not None):
        logger.info("Using parent version information")
        version = parent_version

    else:
        raise Exception("Could not find the version in the pom.xml")

    return (group_id, artif_id, version)


@asyncio.coroutine
def create_pme_result_file(repo_dir):

    result_file_folder = repo_dir + "/target"
    result_file_path = result_file_folder + "/pom-manip-ext-result.json"
            
    # get data by reading the pom.xml directly
    pom_path = repo_dir + "/pom.xml"

    try:
        group_id, artifact_id, version = yield from get_gav_from_pom(pom_path)
    except FileNotFoundError:
        logger.warning("Could not find pom.xml from: " + str(pom_path))
        group_id, artifact_id, version = (None, None, None)

    pme_result = {
        "VersioningState": {
            "executionRootModified": {
                "groupId": group_id,
                "artifactId": artifact_id,
                "version": version
            }
        }
    }

    if not os.path.exists(result_file_folder):
        os.makedirs(result_file_folder)

    with open(result_file_path, 'w') as outfile:
        json.dump(pme_result, outfile)
