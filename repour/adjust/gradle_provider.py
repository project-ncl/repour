import asyncio
import json
import logging
import os
import subprocess

from string import Template

from . import process_provider

logger = logging.getLogger(__name__)

EXECUTION_NAME = "GRADLE"

INIT_SCRIPT_FILE_NAME = "init-align.gradle"
MANIPULATION_FILE_NAME = "manipulation.json"

INIT_SCRIPT_CONTENT = Template("""
initscript {
    repositories {
        flatDir {
            dirs '${lib_dir}'
        }

        mavenLocal()
        mavenCentral()
    }
    dependencies {
        classpath "org.jboss.gm.analyzer:analyzer:${version}"
    }
}

allprojects {
    apply plugin: org.jboss.gm.analyzer.alignment.AlignmentPlugin
}""")


class Chdir(object):
    """ Context manager for changing the current working directory """

    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)


def get_gradle_provider(plugin_version, plugin_lib_dir, default_parameters):

    @asyncio.coroutine
    def adjust(work_dir, extra_adjust_parameters, adjust_result):
        """Generate the manipulation.json file with information about aligned versions"""

        logger.info("Adjusting in {}".format(work_dir))

        with Chdir(work_dir):

            init_file_content = INIT_SCRIPT_CONTENT.substitute(
                version=plugin_version,
                lib_dir=plugin_lib_dir
            )

            logger.info("Writing '{}' init script file".format(
                INIT_SCRIPT_FILE_NAME))

            logger.info(init_file_content)

            with open(INIT_SCRIPT_FILE_NAME, "w") as f:
                f.write(init_file_content)

            cmd = ["./gradlew", "--console", "plain", "--no-daemon", "--stacktrace",
                   "--init-script", INIT_SCRIPT_FILE_NAME, "generateAlignmentMetadata"] + default_parameters

            result = yield from process_provider.get_process_provider(EXECUTION_NAME,
                                                                      cmd,
                                                                      get_result_data=get_result_data,
                                                                      send_log=False)(work_dir, extra_adjust_parameters, adjust_result)

            return result

    @asyncio.coroutine
    def get_result_data(work_dir):
        """ Read the manipulation.json file and return it as an object"""

        logger.info(
            "Reading '{}' file with alignment result".format(MANIPULATION_FILE_NAME))

        with Chdir(work_dir):
            if not os.path.exists(MANIPULATION_FILE_NAME):
                raise Exception("Expected generated alignment file '{}' does not exist".format(
                    MANIPULATION_FILE_NAME))

            with open(MANIPULATION_FILE_NAME, "r") as f:
                return json.load(f)

    return adjust
