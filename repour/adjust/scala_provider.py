import json
import logging
import os

from .. import exception
import shlex

from . import process_provider, pme_provider

logger = logging.getLogger(__name__)

SMEG_MANIPULATION_FILE_NAME = "manipulations.json"


def get_scala_provider(
    execution_name,
    sbt_path,
    default_parameters,
    repour_parameters,
    rest_mode,
    brew_pull_enabled,
    suffix_prefix,
):
    async def get_result_data(
        work_dir,
        extra_adjust_parameters,
        results_file=None,
        group_id=None,
        artifact_id=None,
    ):
        """ Read the manipulations.json file and return it as an object

        Format is:

        {
            VersioningState: {
                executionRootModified: {
                    groupId: "value",
                    artifactId: "value",
                    version: "value"
                }
            },
            RemovedRepositories: []
        }

        """
        manipulation_file_path = os.path.join(work_dir, SMEG_MANIPULATION_FILE_NAME)

        if os.path.isfile(manipulation_file_path):
            file_path = manipulation_file_path
            logger.info("Reading '{}' file with alignment result".format(file_path))

            with open(file_path, "r") as f:
                # SMEG returns manipulations.json file already in correct format
                result = json.load(f)
                if group_id is not None and artifact_id is not None:
                    logger.warning(
                        "Overriding the groupId of the result to: " + group_id
                    )
                    result["VersioningState"]["executionRootModified"][
                        "groupId"
                    ] = group_id

                    logger.warning(
                        "Overriding the artifactId of the result to: " + artifact_id
                    )
                    result["VersioningState"]["executionRootModified"][
                        "artifactId"
                    ] = artifact_id
                return result
        else:
            return {
                "VersioningState": {
                    "executionRootModified": {
                        "groupId": group_id,
                        "artifactId": artifact_id,
                        "version": None,
                    }
                },
                "RemovedRepositories": [],
            }

    async def adjust(work_dir, extra_adjust_parameters, adjust_result):
        alignment_parameters = ["-DrestMode=" + rest_mode]

        extra_parameters = get_extra_parameters(extra_adjust_parameters)

        if suffix_prefix:
            alignment_parameters.append(
                "-DversionIncrementalSuffix=" + suffix_prefix + "-redhat"
            )

        if brew_pull_enabled:
            alignment_parameters.append("-DrestBrewPullActive=true")

        logger.info("SKIPPING " + execution_name + " alignment phase.")

        cmd = (
            [sbt_path]
            + default_parameters
            + extra_parameters
            + repour_parameters
            + alignment_parameters
            + ["manipulate"]
            + ["writeReport"]
        )

        logger.info(
            'Executing "' + execution_name + '" Command is "{cmd}".'.format(**locals())
        )

        result = await process_provider.get_process_provider(
            execution_name, cmd, get_result_data=get_result_data, send_log=True,
        )(work_dir, extra_adjust_parameters, adjust_result)

        (
            override_group_id,
            override_artifact_id,
        ) = await pme_provider.get_extra_param_execution_root_name(
            extra_adjust_parameters
        )

        adjust_result["adjustType"] = result["adjustType"]
        adjust_result["resultData"] = await get_result_data(
            work_dir,
            extra_parameters,
            group_id=override_group_id,
            artifact_id=override_artifact_id,
        )

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
