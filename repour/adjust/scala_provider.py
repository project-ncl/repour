import logging
from . import util
from .. import exception
import shlex

logger = logging.getLogger(__name__)


def get_scala_provider(
    execution_name,
    sbt_ext_path,
    default_parameters,
    repour_parameters,
    specific_indy_group,
    timestamp,
):
    async def get_result_data(work_dir, extra_adjust_parameters, results_file=None):
        template = {
            "VersioningState": {
                "executionRootModified": {
                    "groupId": None,
                    "artifactId": None,
                    "version": None,
                }
            },
            "RemovedRepositories": [],
        }
        return template

    async def get_extra_parameters(extra_adjust_parameters):
        """
        Get the extra ALIGNMENT_PARAMETERS parameters from PNC
        """
        subfolder = ""

        params_string = extra_adjust_parameters.get("ALIGNMENT_PARAMETERS", None)
        if params_string is None:
            return []
        else:
            params = shlex.split(params_string)
            for p in params:
                if p[0] != "-":
                    desc = (
                        'Parameters that do not start with dash "-" are not allowed. '
                        + 'Found "{p}" in "{params}".'.format(**locals())
                    )
                    raise exception.AdjustCommandError(desc, [], 10, stderr=desc)

            return params

    async def adjust(work_dir, extra_adjust_parameters, adjust_result):
        extra_parameters = await get_extra_parameters(extra_adjust_parameters)

        temp_build_parameters = []

        if timestamp:
            orig_inc_suffix = util.get_param_value(
                "-DversionIncrementalSuffix",
                repour_parameters,
                extra_parameters,
                default_parameters,
            )
            temp_suffix = ("-" + orig_inc_suffix) if orig_inc_suffix else ""
            temp_build_parameters.append(
                "-DversionIncrementalSuffix=" + timestamp + temp_suffix
            )

        if specific_indy_group:
            temp_build_parameters.append("-DrestRepositoryGroup=" + specific_indy_group)

        logger.info("SKIPPING " + execution_name + " alignment phase.")

        # TODO uncomment once ready
        # cmd = (
        #     ["java", "-jar", sbt_ext_path]
        #     + default_parameters
        #     + extra_parameters
        #     + repour_parameters
        #     + temp_build_parameters
        # )
        #
        # logger.info(
        #     'Executing "' + execution_name + '" Command is "{cmd}".'.format(**locals())
        # )
        #
        # result = await process_provider.get_process_provider(
        #     execution_name,
        #     cmd,
        #     get_result_data=get_result_data,
        #     send_log=True,
        # )(work_dir, extra_adjust_parameters, adjust_result)

        # TODO mock an empty result and delete once ready
        result = {"adjustType": [], "resultData": {}}
        result["resultData"] = await get_result_data(
            work_dir, extra_adjust_parameters, adjust_result
        )
        result["adjustType"].append(execution_name)

        # TODO will I even get adjustType?
        adjust_result["adjustType"] = result["adjustType"]
        adjust_result["resultData"] = result["resultData"]

        return result

    return adjust
