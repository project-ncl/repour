import logging

from voluptuous import *

from . import adjust as adjustmodule
from . import pull
from . import repo

#
# Primitives
#

nonempty_str = All(str, Length(min=1))
nonempty_noblank_str = All(str, Match(r'\S+'))
port_num = All(int, Range(min=1, max=65535))

#
# Adjust
#

adjust_raw = {
    "name": nonempty_str,
    "ref": nonempty_str,
}

adjust = Schema(
    adjust_raw,
    required=True,
    extra=False,
)

#
# Pull
#

pull_raw = Any(
    {
        "name": nonempty_str,
        "type": Any(*pull.scm_types),
        "ref": nonempty_str,
        "url": Url(),
        Optional("adjust"): bool,
    },
    {
        "name": nonempty_str,
        "type": pull.archive_type,
        "url": Url(),
        Optional("adjust"): bool,
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
    "adjust_provider": {
        "type": Any(*adjustmodule.provider_types.keys()),
        "params": {Extra: object},
    },
    "repo_provider": {
        "type": Any(*repo.provider_types.keys()),
        "params": {Extra: object},
    },
}
server_config = Schema(
    server_config_raw,
    required=True,
    extra=False,
)
