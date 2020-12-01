# flake8: noqa
import json
import logging
import os
import shutil
import subprocess
from string import Template

from .. import asutil
from . import process_provider, util
from repour.lib.scm import git

logger = logging.getLogger(__name__)

EXECUTION_NAME = "GRADLE"

INIT_SCRIPT_FILE_NAME = "analyzer-init.gradle"
MANIPULATION_FILE_NAME = "manipulation.json"

stdout_options = asutil.process_stdout_options
stderr_options = asutil.process_stderr_options


def get_gradle_provider(
    init_file_path,
    gme_jar_path,
    default_parameters,
    repour_parameters,
    default_gradle_path,
    specific_indy_group=None,
    timestamp=None,
):
    async def adjust(work_dir, extra_adjust_parameters, adjust_result):
        """Generate the manipulation.json file with information about aligned versions"""

        if not os.path.exists(init_file_path):
            raise Exception(
                "The Gradle init file '{}' does not exist - are you sure you provided the correct path in configuration?".format(
                    init_file_path
                )
            )

        temp_build_parameters = []

        if timestamp:
            temp_build_parameters.append(
                "-DversionIncrementalSuffix=" + timestamp + "-redhat"
            )

        if specific_indy_group:
            temp_build_parameters.append("-DrestRepositoryGroup=" + specific_indy_group)

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
            + temp_build_parameters
        )

        result = await process_provider.get_process_provider(
            EXECUTION_NAME,
            cmd,
            get_result_data=get_result_data,
            send_log=True,
            results_file=MANIPULATION_FILE_NAME,
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

        adjust_result["adjustType"] = result["adjustType"]
        adjust_result["resultData"] = result["resultData"]

        return result

    async def get_result_data(work_dir, extra_parameters, results_file=None):
        """ Read the manipulation.json file and return it as an object

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

        manipulation_file_path = os.path.join(work_dir, MANIPULATION_FILE_NAME)

        logger.info(
            "Reading '{}' file with alignment result".format(manipulation_file_path)
        )

        if os.path.exists(manipulation_file_path):

            with open(manipulation_file_path, "r") as f:
                result = json.load(f)
                template["VersioningState"]["executionRootModified"][
                    "groupId"
                ] = result["group"]
                template["VersioningState"]["executionRootModified"][
                    "artifactId"
                ] = result["name"]
                template["VersioningState"]["executionRootModified"][
                    "version"
                ] = result["version"]

            try:
                template["RemovedRepositories"] = util.get_removed_repos(
                    work_dir, default_parameters
                )
            except FileNotFoundError as e:
                logger.error("File for removed repositories could not be found")
                logger.error(str(e))

        return template

    return adjust


def gradlew_path_present(work_dir):
    return os.path.exists(os.path.join(work_dir, "gradlew"))


def gme_repos_dot_gradle_present(work_dir):
    return os.path.exists(os.path.join(work_dir, "gradle", "gme-repos.gradle"))
