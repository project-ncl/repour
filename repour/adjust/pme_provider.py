# flake8: noqa
import json
import logging
import os
import re
import shlex
import xml.etree.ElementTree as ET
from xml.dom import minidom

from repour import exception
from repour.adjust import process_provider, util

logger = logging.getLogger(__name__)


# TODO: NCL-3503: Finish implementation once the other components are figured out
def get_pme_provider(
    execution_name,
    pme_jar_path,
    default_parameters,
    repour_parameters,
    rest_mode,
    output_to_logs=False,
    brew_pull_enabled=False,
    suffix_prefix=None,
    temp_prefer_persistent_enabled=False,
):
    async def get_result_data(
        work_dir, extra_parameters, group_id=None, artifact_id=None, results_file=None
    ):

        if results_file:
            result_file_path_manipulation = results_file
        else:
            result_file_path_manipulation = work_dir + "/target/manipulation.json"
            result_file_path_alignment_report = (
                work_dir + "/target/alignmentReport.json"
            )

        pme_and_extra_params = default_parameters.copy()
        pme_and_extra_params.extend(extra_parameters)
        pme_and_extra_params.extend(repour_parameters)

        file_path = None
        if os.path.isfile(result_file_path_alignment_report):
            file_path = result_file_path_alignment_report
        elif os.path.isfile(result_file_path_manipulation):
            file_path = result_file_path_manipulation

        if file_path is not None:
            with open(file_path, "r") as file:
                logger.info("Getting results from file: " + file_path)
                return parse_pme_result_manipulation_format(
                    work_dir, pme_and_extra_params, file.read(), group_id, artifact_id
                )
        else:
            logger.warn("Couldn't capture any result file from PME")
            return None

    async def adjust(repo_dir, extra_adjust_parameters, adjust_result):
        nonlocal execution_name

        alignment_parameters = ["-DrestMode=" + rest_mode]

        if suffix_prefix:
            alignment_parameters.append(
                "-DversionIncrementalSuffix=" + suffix_prefix + "-redhat"
            )

        if brew_pull_enabled:
            alignment_parameters.append("-DrestBrewPullActive=true")

        suffix_prefix_no_temporary = util.strip_temporary_from_prefix(suffix_prefix)
        # NCLSUP-669: specify the versionSuffixAlternatives if we prefer persistent build alignment for the temp build
        # and the suffix_prefix without the temporary string is not empty (e.g for managedsvc)
        if temp_prefer_persistent_enabled and suffix_prefix_no_temporary:
            alignment_parameters.append(
                "-DversionSuffixAlternatives=redhat,"
                + suffix_prefix_no_temporary
                + "-redhat"
            )

        extra_parameters, subfolder = util.get_extra_parameters(extra_adjust_parameters)

        jvm_version = util.get_jvm_from_extra_parameters(extra_parameters)

        if jvm_version:
            location = "/usr/lib/jvm/java-" + jvm_version + "-openjdk/bin/"
            logger.info("Specifying java path: " + location)
        else:
            location = ""

        await util.print_java_version(java_bin_dir=location)

        # readjust the repo_dir to run PME from the folder where the root pom.xml is located
        # See: PRODTASKS-361
        repo_dir = os.path.join(repo_dir, subfolder)
        log_context_value = await util.generate_user_context()
        log_context_parameter = ["-DrestHeaders=" + log_context_value]
        util.verify_folder_exists(
            repo_dir,
            "'{}' path specified in alignment parameters doesn't exist".format(
                subfolder
            ),
        )

        cmd = (
            [location + "java", "-jar", pme_jar_path]
            + default_parameters
            + extra_parameters
            + repour_parameters
            + alignment_parameters
            + log_context_parameter
        )

        logger.info(
            'Executing "'
            + execution_name
            + '" using "pme" adjust provider '
            + '(delegating to "process" provider). Command is "{cmd}".'.format(
                **locals()
            )
        )

        res = await process_provider.get_process_provider(
            execution_name,
            cmd,
            get_result_data=get_result_data,
            send_log=output_to_logs,
        )(repo_dir, extra_adjust_parameters, adjust_result)

        pme_disabled = is_pme_disabled_via_extra_parameters(extra_adjust_parameters)

        if pme_disabled:
            logger.warning("PME is disabled via extra parameters")
            await create_pme_result_file(repo_dir)
        (
            override_group_id,
            override_artifact_id,
        ) = await get_extra_param_execution_root_name(extra_adjust_parameters)

        adjust_result["resultData"] = await get_result_data(
            repo_dir, extra_parameters, override_group_id, override_artifact_id
        )
        return res

    return adjust


async def get_extra_param_execution_root_name(extra_adjust_parameters):
    """
    If the parameter 'BREW_BUILD_NAME' is present, the string value should be in format '<group_id>:<artifact_id>'

    Return the group_id,artifact_id value.

    If the string is in the wrong format or if the parameter is not present, return None,None instead
    """
    paramsString = extra_adjust_parameters.get("BREW_BUILD_NAME", None)

    if paramsString is None:
        return None, None
    else:
        result = paramsString.split(":")
        if len(result) == 2:
            return result[0], result[1]
        else:
            logger.warning(
                'BREW_BUILD_NAME parameter has as value the wrong format. It should be "<group_id>:<artifact_id>"'
            )
            logger.warning('Value provided is: "' + paramsString + '"')
            return None, None


async def get_version_from_pme_result(pme_result):
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
        version = pme_result["VersioningState"]["executionRootModified"]["version"]
        return version
    except Exception as e:
        logger.error("Couldn't extract PME result version from JSON file")
        logger.error(e)
        return None


async def get_gav_from_pom(pom_xml_file):

    tree = ET.parse(pom_xml_file)
    root = tree.getroot()

    if "{" in root.tag and "}" in root.tag:
        namespace_search = "{{{}}}".format(root.tag.split("}")[0].strip("{"))
    else:
        namespace_search = ""

    parent = root.find(namespace_search + "parent")
    parent_group_id = None
    parent_version = None

    # https://maven.apache.org/pom.html#Maven_Coordinates
    # Docs concerning how inheritance of groupId and version from parent
    if parent is not None:

        parent_group_id_elem = parent.find(namespace_search + "groupId")
        parent_version_elem = parent.find(namespace_search + "version")

        if parent_group_id_elem is not None:
            parent_group_id = parent_group_id_elem.text

        if parent_version_elem is not None:
            parent_version = parent_version_elem.text

    group_id_elem = root.find(namespace_search + "groupId")

    if group_id_elem is not None:
        group_id = group_id_elem.text

    elif (group_id_elem is None) and (parent_group_id is not None):
        logger.info("Using parent groupId information")
        group_id = parent_group_id

    else:
        raise Exception("Could not find the groupId in the pom.xml")

    artif_id_elem = root.find(namespace_search + "artifactId")

    if artif_id_elem is not None:
        artif_id = artif_id_elem.text
    else:
        raise Exception("Could not find the artifactId in the pom.xml")

    version_elem = root.find(namespace_search + "version")

    if version_elem is not None:
        version = version_elem.text

    elif (version_elem is None) and (parent_version is not None):
        logger.info("Using parent version information")
        version = parent_version

    else:
        raise Exception("Could not find the version in the pom.xml")

    return (group_id, artif_id, version)


async def create_pme_result_file(repo_dir):

    result_file_folder = repo_dir + "/target"
    result_file_path = result_file_folder + "/alignmentReport.json"

    # get data by reading the pom.xml directly
    pom_path = repo_dir + "/pom.xml"

    try:
        group_id, artifact_id, version = await get_gav_from_pom(pom_path)
    except FileNotFoundError:
        logger.warning("Could not find pom.xml from: " + str(pom_path))
        group_id, artifact_id, version = (None, None, None)

    pme_result = {
        "executionRoot": {
            "groupId": group_id,
            "artifactId": artifact_id,
            "version": version,
        }
    }

    if not os.path.exists(result_file_folder):
        os.makedirs(result_file_folder)

    with open(result_file_path, "w") as outfile:
        json.dump(pme_result, outfile)


def parse_pme_result_manipulation_format(
    work_dir, pme_parameters, raw_result_data, group_id, artifact_id
):

    logger.info('Got PME result data: "{raw_result_data}".'.format(**locals()))
    data = json.loads(raw_result_data)

    pme_result = {"VersioningState": {"executionRootModified": {}}}

    if group_id is not None and artifact_id is not None:
        logger.warning("Overriding the groupId of the result to: " + group_id)
        pme_result["VersioningState"]["executionRootModified"]["groupId"] = group_id

        logger.warning("Overriding the artifactId of the result to: " + artifact_id)
        pme_result["VersioningState"]["executionRootModified"][
            "artifactId"
        ] = artifact_id

    else:
        pme_result["VersioningState"]["executionRootModified"]["groupId"] = data[
            "executionRoot"
        ]["groupId"]
        pme_result["VersioningState"]["executionRootModified"]["artifactId"] = data[
            "executionRoot"
        ]["artifactId"]

    # Set version if present in result file
    if "executionRoot" in data and "version" in data["executionRoot"]:
        pme_result["VersioningState"]["executionRootModified"]["version"] = data[
            "executionRoot"
        ]["version"]

    try:
        pme_result["RemovedRepositories"] = util.get_removed_repos(
            work_dir, pme_parameters
        )
    except FileNotFoundError as e:
        logger.error("File for removed repositories could not be found")
        logger.error(str(e))

    return pme_result


def is_pme_disabled_via_extra_parameters(extra_adjust_parameters):
    """
    Check if PME is disabled via one of the parameters passed to PME by the user

    return: :bool:
    """
    paramsString = extra_adjust_parameters.get("ALIGNMENT_PARAMETERS", None)

    if paramsString is None:
        return False

    else:

        try:
            params = shlex.split(paramsString)

            for p in params:

                if p.startswith("-Dmanipulation.disable=true"):
                    return True
            else:
                return False
        except Exception as e:
            # it's a failed user error, not a system error
            raise exception.AdjustCommandError(str(e), [], 10, stderr=str(e))
