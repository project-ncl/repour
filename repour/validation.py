import logging

from voluptuous import *

from . import pull
from . import repo

#
# Primitives
#

nonempty_str = All(str, Length(min=1))
nonempty_noblank_str = All(str, Match(r'\S+'))
port_num = All(int, Range(min=1, max=65535))

#
# Sync
#

pull_raw = Any(
    {
        "name": nonempty_str,
        "type": Any(*pull.scm_types),
        "tag": nonempty_str,
        "url": Url(),
    },
    {
        "name": nonempty_str,
        "type": pull.archive_type,
        "url": Url(),
    },
)
pull = Schema(
    pull_raw,
    required=True,
    extra=False,
)

#
# Server configuration
#

server_config_raw = {
    "log": {
        "path": nonempty_str,
        "level": Any(*logging._nameToLevel.keys()),
    },
    "bind": {
        "address": Any(nonempty_str, None),
        "port": port_num,
    },
    "repo_provider": {
        "type": Any(*repo.provider_types.keys()),
        "url": Url(),
    },
}
server_config = Schema(
    server_config_raw,
    required=True,
    extra=False,
)
