import asyncio
import json
import logging
import os
import shlex

from . import process_provider

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
        return json.loads(raw_result_data)

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
                    raise Exception('Parameters that do not start with dash "-" are not allowed. '
                                    + 'Found "{p}" in "{params}".'.format(**locals()))
                if p.startswith("--file"):
                    subfolder = p.replace("--file=", "").replace("pom.xml", "")

            params_without_file_option = [p for p in params if not p.startswith("--file=")]

            return params_without_file_option, subfolder

    @asyncio.coroutine
    def adjust(repo_dir, extra_adjust_parameters, adjust_result):

        nonlocal execution_name

        extra_parameters, subfolder = yield from get_extra_parameters(extra_adjust_parameters)

        # readjust the repo_dir to run PME from the folder where the root pom.xml is located
        # See: PRODTASKS-361
        repo_dir = os.path.join(repo_dir, subfolder)

        cmd = ["java", "-jar", pme_jar_path] \
              + pme_parameters + extra_parameters

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
