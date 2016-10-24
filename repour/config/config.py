import json
import logging
import os

import asyncio

logger = logging.getLogger(__name__)

CONFIG_FILE_PATH_ENV_PROPERTY_NAME = 'REPOUR_CONFIG_FILE_PATH'

_cached_configuration = None

@asyncio.coroutine
def get_configuration():
    global _cached_configuration

    def get_config_file_path():
        config_file_path = os.environ.get(CONFIG_FILE_PATH_ENV_PROPERTY_NAME,
                                          os.path.dirname(os.path.realpath(__file__)) + '/default-config.json')

        if not os.path.isfile(config_file_path):
            raise Exception("Could not find configuration file '" + config_file_path + "'.")

        return config_file_path

    @asyncio.coroutine
    def load_configuration(config_file_path):
        f = None
        try:
            f = open(config_file_path, 'r')
            return json.load(f)
        finally:
            if f is not None:
                f.close()

    if _cached_configuration is None:
        _cached_configuration = yield from load_configuration(get_config_file_path())

    return _cached_configuration
