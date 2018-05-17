import asyncio
import json
import logging
import os
import shlex
import re

import xml.etree.ElementTree as ET

from . import process_provider
from .. import exception
from xml.dom import minidom

logger = logging.getLogger(__name__)


# TODO: NCL-3503: Finish implementation once the other components are figured out
def get_pme_provider(execution_name, pme_jar_path, pme_parameters, output_to_logs=False, specific_indy_group=None, timestamp=None):

    @asyncio.coroutine
    def get_result_data(work_dir, pme_disabled):
        if pme_disabled:

            logger.warn("PME disabled via parameters! Getting Maven information by parsing pom.xml directly")
            
            # get data by reading the pom.xml directly
            result_file_path = work_dir + "/pom.xml"

            try:
                group_id, artifact_id, version = get_gav_from_pom(results_file_path)
            except FileNotFoundError:
                logger.warn("Could not find pom.xml from: " + str(results_file_path))
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

        else:
            raw_result_data = "{}"
            result_file_path = work_dir + "/target/pom-manip-ext-result.json"

            if os.path.isfile(result_file_path):
                with open(result_file_path, "r") as file:
                    raw_result_data = file.read()

            logger.info('Got PME result data "{raw_result_data}".'.format(**locals()))
            pme_result = json.loads(raw_result_data)

        try:
            pme_result["RemovedRepositories"] = get_removed_repos(work_dir, pme_parameters)
        except FileNotFoundError as e:
            logger.error('File for removed repositories could not be found')
            logger.error(str(e))

        return pme_result

    def get_gav_from_pom(pom_xml_file):

        tree = ET.parse(pom_xml_file)
        root = tree.getroot()

        namespace = root.tag.split('}')[0].strip('{')

        group_id = root.find('{{{}}}groupId'.format(namespace)).text
        artif_id = root.find('{{{}}}artifactId'.format(namespace)).text
        version  = root.find('{{{}}}version'.format(namespace)).text

        return (group_id, artif_id, version)


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

    def get_removed_repos(work_dir, parameters):
        """
        Parses the filename of the removed repos backup file from the parameters list and if there
        is one, it reads the list of repos and returns it.
        """
        result = []

        pattern = re.compile("-DrepoRemovalBackup[ =](.+)")
        for parameter in parameters:
            m = pattern.match(parameter)
            if m is not None:
                filepath = os.path.join(work_dir, m.group(1))
                logger.debug('Files and folders in the work directory:\n  %s', os.listdir(work_dir))

                if os.path.exists(filepath):
                    tree = minidom.parse(filepath)
                    for repo_elem in tree.getElementsByTagName("repository"):
                        repo = {"releases": True, "snapshots": True, "name": "", "id": "", "url": ""}
                        for enabled_elem in repo_elem.getElementsByTagName("enabled"):
                            if enabled_elem.parentNode.localName in ["releases", "snapshots"]:
                                bool_value = enabled_elem.childNodes[0].data == "true"
                                repo[enabled_elem.parentNode.localName] = bool_value
                        for tag in ["id", "name", "url"]:
                            for elem in repo_elem.getElementsByTagName(tag):
                                repo[tag] = elem.childNodes[0].data
                        result.append(repo)
                    break
                else:
                    logger.info('File %s does not exist. It seems no repositories were removed '
                                'by PME.', filepath)

        return result

    @asyncio.coroutine
    def get_extra_parameters(extra_adjust_parameters):
        """
        Get the extra PME parameters from PNC
        If the PME parameters contain '--file=<folder>/pom.xml', then extract that folder
        and remove that --file option from the list of extra params.
        In PME 2.11 and PME 2.12, there is a bug where that option causes the file target/pom-manip-ext-result.json
        to be badly generated. Fixed in PME 2.13+
        See: PRODTASKS-361
        Returns: tuple<list<string>, string>: list of params(minus the --file option), and folder where to run PME
        If '--file' option not used, the folder will be an empty string
        """
        subfolder = ''

        paramsString = extra_adjust_parameters.get("CUSTOM_PME_PARAMETERS", None)
        if paramsString is None:
            return [], subfolder
        else:
            params = shlex.split(paramsString)
            for p in params:
                if p[0] != "-":
                    desc = ('Parameters that do not start with dash "-" are not allowed. '
                            + 'Found "{p}" in "{params}".'.format(**locals()))
                    raise exception.AdjustCommandError(desc, [], 10, stderr=desc)
                if p.startswith("--file"):
                    subfolder = p.replace("--file=", "").replace("pom.xml", "")

            params_without_file_option = [p for p in params if not p.startswith("--file=")]

            return params_without_file_option, subfolder

    @asyncio.coroutine
    def adjust(repo_dir, extra_adjust_parameters, adjust_result):
        nonlocal execution_name

        temp_build_parameters = []
        if timestamp:
            temp_build_parameters.append("-DversionIncrementalSuffix=" + timestamp + "-redhat")

        if specific_indy_group:
            temp_build_parameters.append("-DrestRepositoryGroup=" + specific_indy_group)

        extra_parameters, subfolder = yield from get_extra_parameters(extra_adjust_parameters)

        # readjust the repo_dir to run PME from the folder where the root pom.xml is located
        # See: PRODTASKS-361
        repo_dir = os.path.join(repo_dir, subfolder)

        cmd = ["java", "-jar", pme_jar_path] \
              + pme_parameters + temp_build_parameters + extra_parameters

        logger.info('Executing "' + execution_name + '" using "pme" adjust provider '
                    + '(delegating to "process" provider). Command is "{cmd}".'.format(**locals()))

        res = yield from process_provider.get_process_provider(execution_name,
                                                     cmd,
                                                     get_result_data=get_result_data,
                                                     send_log=output_to_logs) \
            (repo_dir, extra_adjust_parameters, adjust_result)

        pme_disabled = is_pme_disabled_via_extra_parameters(extra_adjust_parameters)

        adjust_result['resultData'] = yield from get_result_data(repo_dir, pme_disabled)
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
