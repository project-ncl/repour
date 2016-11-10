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
