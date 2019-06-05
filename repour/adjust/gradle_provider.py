import asyncio
import json
import logging
import os
import shutil
import subprocess

from string import Template

from . import process_provider
from .. import asutil

logger = logging.getLogger(__name__)

EXECUTION_NAME = "GRADLE"

INIT_SCRIPT_FILE_NAME = "analyzer-init.gradle"
MANIPULATION_FILE_NAME = "manipulation.json"


def get_gradle_provider(init_file_path, default_parameters):

    @asyncio.coroutine
    def adjust(work_dir, extra_adjust_parameters, adjust_result):
        """Generate the manipulation.json file with information about aligned versions"""

        if not os.path.exists(init_file_path):
            raise Exception(
                "The Gradle init file '{}' does not exist - are you sure you provided the correct path in configuration?".format(init_file_path))

        logger.info("Adjusting in {}".format(work_dir))
        logger.info("Copying Gradle init file from '{}'".format(init_file_path))
        shutil.copy2(init_file_path, os.path.join(
            work_dir, INIT_SCRIPT_FILE_NAME))

        logger.info("Getting Gradle version...")

        expect_ok = asutil.expect_ok_closure()

        yield from expect_ok(
            cmd=["./gradlew", "--version"],
            desc="Failed getting Gradle version",
            cwd=work_dir,
            live_log=True
        )

        cmd = ["./gradlew", "--console", "plain", "--no-daemon", "--stacktrace",
               "--init-script", INIT_SCRIPT_FILE_NAME, "generateAlignmentMetadata"] + default_parameters

        result = yield from process_provider.get_process_provider(EXECUTION_NAME,
                                                                  cmd,
                                                                  get_result_data=get_result_data,
                                                                  send_log=True)(work_dir, extra_adjust_parameters, adjust_result)

        return result

    @asyncio.coroutine
    def get_result_data(work_dir):
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
                    "version": None
                }
            },
            "RemovedRepositories": []
        }

        # TODO: populate RemoveRepositories in the future

        manipulation_file_path = os.path.join(work_dir, MANIPULATION_FILE_NAME)

        logger.info(
            "Reading '{}' file with alignment result".format(manipulation_file_path))

        if not os.path.exists(manipulation_file_path):
            raise Exception("Expected generated alignment file '{}' does not exist".format(
                manipulation_file_path))

        with open(manipulation_file_path, "r") as f:
            result = json.load(f)
            template["VersioningState"]["executionRootModified"]["groupId"] = result["group"]
            template["VersioningState"]["executionRootModified"]["artifactId"] = result["name"]
            template["VersioningState"]["executionRootModified"]["version"] = result["version"]

            return template

    return adjust
