import logging
from .. import exception
import shlex

logger = logging.getLogger(__name__)


def get_scala_provider(
    execution_name,
    sbt_ext_path,
    default_parameters,
    repour_parameters,
    rest_mode,
    brew_pull_enabled,
    suffix_prefix,
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

    async def adjust(work_dir, extra_adjust_parameters, adjust_result):
        alignment_parameters = ["-DrestMode=" + rest_mode]

        if suffix_prefix:
            alignment_parameters.append(
                "-DversionIncrementalSuffix=" + suffix_prefix + "-redhat"
            )

        if brew_pull_enabled:
            alignment_parameters.append("-DrestBrewPullActive=true")

        logger.info("SKIPPING " + execution_name + " alignment phase.")

        # TODO uncomment once ready
        # cmd = (
        #     ["java", "-jar", sbt_ext_path]
        #     + default_parameters
        #     + extra_parameters
        #     + repour_parameters
        #     + alignment_parameters
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


def get_extra_parameters(extra_adjust_parameters):
    """
    Get the extra ALIGNMENT_PARAMETERS parameters from PNC
    """
    subfolder = ""

    params_string = extra_adjust_parameters.get("ALIGNMENT_PARAMETERS", None)
    if params_string is None:
        return []
    else:
        try:
            params = shlex.split(params_string)
        except Exception as e:
            # it's a failed user error, not a system error
            raise exception.AdjustCommandError(str(e), [], 10, stderr=str(e))

        for p in params:
            if p[0] != "-":
                desc = (
                    'Parameters that do not start with dash "-" are not allowed. '
                    + 'Found "{p}" in "{params}".'.format(**locals())
                )
                raise exception.AdjustCommandError(desc, [], 10, stderr=desc)

        return params
