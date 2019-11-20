import asyncio
import json
import logging
import os
import shutil
import subprocess

from string import Template

from . import process_provider
from . import util
from .. import asutil

logger = logging.getLogger(__name__)

EXECUTION_NAME = "GRADLE"

INIT_SCRIPT_FILE_NAME = "analyzer-init.gradle"
MANIPULATION_FILE_NAME = "manipulation.json"

stdout_options = asutil.process_stdout_options
stderr_options = asutil.process_stderr_options

def get_gradle_provider(init_file_path, gme_jar_path, default_parameters, specific_indy_group=None, timestamp=None):

    @asyncio.coroutine
    def adjust(work_dir, extra_adjust_parameters, adjust_result):
        """Generate the manipulation.json file with information about aligned versions"""

        if not os.path.exists(init_file_path):
            raise Exception(
                "The Gradle init file '{}' does not exist - are you sure you provided the correct path in configuration?".format(init_file_path))

        temp_build_parameters = []

        if timestamp:
            temp_build_parameters.append(
                "-DversionIncrementalSuffix=" + timestamp + "-redhat")

        if specific_indy_group:
            temp_build_parameters.append(
                "-DrestRepositoryGroup=" + specific_indy_group)

        extra_parameters, subfolder = yield from util.get_extra_parameters(extra_adjust_parameters)

        work_dir = os.path.join(work_dir, subfolder)

        logger.info("Adjusting in {}".format(work_dir))

        logger.info("Getting Gradle version...")

        expect_ok = asutil.expect_ok_closure()

        jvm_version = util.get_jvm_from_extra_parameters(extra_parameters)

        if jvm_version:
            location = '/usr/lib/jvm/java-' + jvm_version + '-openjdk/bin/'
            logger.info("Specifying java path: " + location)
        else:
            location = ''

        default_parameters.append("--target=" + work_dir)
        default_parameters.append("--init-script=" + init_file_path)

        yield from util.print_java_version(java_bin_dir=location)

        cmd = [location + "java", "-jar", gme_jar_path] \
              + default_parameters + temp_build_parameters + extra_parameters

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

        try:
            template["RemovedRepositories"] = util.get_removed_repos(
                work_dir, default_parameters)
        except FileNotFoundError as e:
            logger.error('File for removed repositories could not be found')
            logger.error(str(e))

        return template

    return adjust
