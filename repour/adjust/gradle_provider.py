# flake8: noqa
import json
import logging
import os
import shutil
import subprocess
from string import Template

from repour import asutil
from repour.adjust import pme_provider, process_provider, util
from repour.lib.scm import git

logger = logging.getLogger(__name__)

EXECUTION_NAME = "GRADLE"

INIT_SCRIPT_FILE_NAME = "analyzer-init.gradle"
ALIGNMENT_REPORT_FILE_NAME = "build/alignmentReport.json"
GME_MANIPULATION_FILE_NAME = "manipulation.json"

stdout_options = asutil.process_stdout_options
stderr_options = asutil.process_stderr_options


def get_gradle_provider(
    init_file_path,
    gme_jar_path,
    default_parameters,
    repour_parameters,
    default_gradle_path,
    rest_mode,
    brew_pull_enabled=False,
    suffix_prefix=None,
    temp_prefer_persistent_enabled=False,
):
    async def adjust(work_dir, extra_adjust_parameters, adjust_result):
        """Generate the manipulation.json file with information about aligned versions"""

        if not os.path.exists(init_file_path):
            raise Exception(
                "The Gradle init file '{}' does not exist - are you sure you provided the correct path in configuration?".format(
                    init_file_path
                )
            )

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

        extra_parameters, subfolder = util.get_extra_parameters(
            extra_adjust_parameters, flags=("-t", "--target")
        )

        work_dir = os.path.join(work_dir, subfolder)
        util.verify_folder_exists(
            work_dir,
            "'{}' path specified in alignment parameter doesn't exist".format(
                subfolder
            ),
        )

        logger.info("Adjusting in {}".format(work_dir))

        jvm_version = util.get_jvm_from_extra_parameters(extra_parameters)

        if jvm_version:
            location = "/usr/lib/jvm/java-" + jvm_version + "-openjdk/bin/"
            logger.info("Specifying java path: " + location)
        else:
            location = ""

        await util.print_java_version(java_bin_dir=location)

        target_and_init = ["--target=" + work_dir, "--init-script=" + init_file_path]

        if not gradlew_path_present(work_dir):
            target_and_init.append("-l=" + default_gradle_path)

        cmd = (
            [location + "java", "-jar", gme_jar_path]
            + default_parameters
            + target_and_init
            + extra_parameters
            + repour_parameters
            + alignment_parameters
        )

        result = await process_provider.get_process_provider(
            EXECUTION_NAME,
            cmd,
            get_result_data=get_result_data,
            send_log=True,
        )(work_dir, extra_adjust_parameters, adjust_result)

        if gme_repos_dot_gradle_present(work_dir):
            logger.info(
                "Explicitly adding file {}".format(
                    os.path.join(work_dir, "gradle", "gme-repos.gradle")
                )
            )
            await git.add_file(
                work_dir, os.path.join("gradle", "gme-repos.gradle"), force=True
            )
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

    async def get_result_data(
        work_dir, extra_parameters, results_file=None, group_id=None, artifact_id=None
    ):
        """Read the manipulation.json file and return it as an object

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

        alignment_report_file_path = os.path.join(work_dir, ALIGNMENT_REPORT_FILE_NAME)
        manipulation_file_path = os.path.join(work_dir, GME_MANIPULATION_FILE_NAME)

        if os.path.isfile(alignment_report_file_path):
            file_path = alignment_report_file_path
            logger.info("Reading '{}' file with alignment result".format(file_path))
            return pme_provider.parse_pme_result_manipulation_format(
                work_dir,
                default_parameters,
                open(file_path).read(),
                group_id,
                artifact_id,
            )
        elif os.path.isfile(manipulation_file_path):
            file_path = manipulation_file_path
            logger.info("Reading '{}' file with alignment result".format(file_path))
            return parse_gme_manipulation_json(
                work_dir, file_path, default_parameters, group_id, artifact_id
            )
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

    return adjust


def gradlew_path_present(work_dir):
    return os.path.exists(os.path.join(work_dir, "gradlew"))


def gme_repos_dot_gradle_present(work_dir):
    return os.path.exists(os.path.join(work_dir, "gradle", "gme-repos.gradle"))


def parse_gme_manipulation_json(
    work_dir, file_path, default_parameters, group_id=None, artifact_id=None
):
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

    with open(file_path, "r") as f:
        result = json.load(f)
        template["VersioningState"]["executionRootModified"]["groupId"] = result[
            "group"
        ]
        template["VersioningState"]["executionRootModified"]["artifactId"] = result[
            "name"
        ]
        template["VersioningState"]["executionRootModified"]["version"] = result[
            "version"
        ]

    if group_id is not None and artifact_id is not None:
        logger.warning("Overriding the groupId of the result to: " + group_id)
        template["VersioningState"]["executionRootModified"]["groupId"] = group_id

        logger.warning("Overriding the artifactId of the result to: " + artifact_id)
        template["VersioningState"]["executionRootModified"]["artifactId"] = artifact_id

    try:
        template["RemovedRepositories"] = util.get_removed_repos(
            work_dir, default_parameters
        )
    except FileNotFoundError as e:
        logger.error("File for removed repositories could not be found")
        logger.error(str(e))

    return template
