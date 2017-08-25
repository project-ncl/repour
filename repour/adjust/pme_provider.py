import asyncio
import json
import logging
import os
import shlex
import re

from . import process_provider
from xml.dom import minidom

logger = logging.getLogger(__name__)


def get_pme_provider(execution_name, pme_jar_path, pme_parameters, output_to_logs=False):
    @asyncio.coroutine
    def get_result_data(work_dir):
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
                logger.info('Files and folders in the work directory:')
                logger.info(os.listdir(work_dir))

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

        return result

    @asyncio.coroutine
    def get_extra_parameters(extra_adjust_parameters):
        paramsString = extra_adjust_parameters.get("CUSTOM_PME_PARAMETERS", None)
        if paramsString is None:
            return []
        else:
            params = shlex.split(paramsString)
            for p in params:
                if p[0] != "-":
                    raise Exception('Parameters that do not start with dash "-" are not allowed. '
                                    + 'Found "{p}" in "{params}".'.format(**locals()))
            return params

    @asyncio.coroutine
    def adjust(repo_dir, extra_adjust_parameters, adjust_result):
        nonlocal execution_name
        cmd = ["java", "-jar", pme_jar_path] \
              + pme_parameters \
              + (yield from get_extra_parameters(extra_adjust_parameters))
        logger.info('Executing "' + execution_name + '" using "pme" adjust provider '
                    + '(delegating to "process" provider). Command is "{cmd}".'.format(**locals()))
        res = yield from process_provider.get_process_provider(execution_name,
                                                     cmd,
                                                     get_result_data=get_result_data,
                                                     send_log=output_to_logs) \
            (repo_dir, extra_adjust_parameters, adjust_result)
        adjust_result['resultData'] = yield from get_result_data(repo_dir)
        return res

    return adjust
