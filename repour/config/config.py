# flake8: noqa
import json
import logging
import os

logger = logging.getLogger(__name__)

CONFIG_FILE_PATH_ENV_PROPERTY_NAME = "REPOUR_CONFIG_FILE_PATH"

_cached_configuration = None


async def get_configuration():
    return get_configuration_sync()


def get_configuration_sync():
    global _cached_configuration

    def get_config_file_path():
        config_file_path = os.environ.get(
            CONFIG_FILE_PATH_ENV_PROPERTY_NAME,
            os.path.dirname(os.path.realpath(__file__)) + "/default-config.json",
        )

        if not os.path.isfile(config_file_path):
            raise Exception(
                "Could not find configuration file '" + config_file_path + "'."
            )

        return config_file_path

    def load_configuration(config_file_path):
        f = None
        try:
            f = open(config_file_path, "r")
            return json.load(f)
        finally:
            if f is not None:
                f.close()

    if _cached_configuration is None:
        config_file_path = get_config_file_path()
        _cached_configuration = load_configuration(config_file_path)
        logger.info(
            "Loaded configuration '"
            + str(_cached_configuration)
            + "' from '"
            + str(config_file_path)
            + "'."
        )

    return _cached_configuration
