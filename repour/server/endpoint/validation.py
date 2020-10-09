# flake8: noqa
import logging

from voluptuous import *

from ...adjust import adjust as adjustmodule
from ... import repo
from giturlparse import validate as validate_git_url


@message("expected a GitUrl", cls=UrlInvalid)
def GitUrl(value):
    """ Validates whether passed value is valid url for git
        If the value is invalid, the method raises an Exception
    """
    t = validate_git_url(value)
    if not t:
        raise ValueError
    return value


def mode_b_ify(raw):
    clone = raw.copy()
    del clone["name"]
    clone["internal_url"] = {
        "readwrite": Url(),  # pylint: disable=no-value-for-parameter
        "readonly": Url(),  # pylint: disable=no-value-for-parameter
    }
    return clone


#
# Primitives
#

nonempty_str = All(str, Length(min=1))
nonempty_noblank_str = All(str, Match(r"^\S+$"))
port_num = All(int, Range(min=1, max=65535))
name_str = Match(r"^[a-zA-Z0-9_.][a-zA-Z0-9_.-]*(?<!\.git)$")

null_or_str = Any(None, nonempty_str)

#
# Callback
#

callback_raw = {
    "url": Url(),  # pylint: disable=no-value-for-parameter
    Optional("method"): Any("PUT", "POST"),
}

callback = Schema({"callback": callback_raw}, required=True, extra=True)

#
# Adjust
#

adjust_raw = {
    "name": name_str,
    "ref": nonempty_str,
    Optional("adjustParameters"): All(dict),
    Optional("originRepoUrl"): Any(None, str),
    Optional("sync"): bool,
    Optional("callback"): callback_raw,
    Optional("tempBuild"): bool,
    Optional("tempBuildTimestamp"): null_or_str,
    Optional("taskId"): null_or_str,
    Optional("buildType"): nonempty_str,
    Optional("defaultAlignmentParams"): Any(None, str),
}

adjust = Schema(adjust_raw, required=True, extra=False)

adjust_modeb = Schema(mode_b_ify(adjust_raw), required=True, extra=False)

external_to_internal = Schema(
    {"external_url": nonempty_str}, required=True, extra=False
)

internal_scm = Schema(
    {
        "project": nonempty_noblank_str,
        "owner_groups": [nonempty_noblank_str],
        Optional("description"): null_or_str,
        Optional("parent_project"): null_or_str,
        Optional("callback"): callback_raw,
    }
)

#
# Clone
#

clone_raw = {
    "type": "git",  # only git supported for now
    Optional("ref"): null_or_str,
    "originRepoUrl": Any(Url(), GitUrl()),  # pylint: disable=no-value-for-parameter
    "targetRepoUrl": Url(),  # pylint: disable=no-value-for-parameter
    Optional("callback"): callback_raw,
}

clone = Schema(clone_raw, required=True, extra=False)


#
# Returns
#

error_validation = Schema(
    [{"error_message": str, "path": [str], "error_type": str}],
    required=True,
    extra=False,
)

error_described = Schema(
    {"error_type": nonempty_str, "error_traceback": nonempty_str, str: object},
    required=True,
    extra=False,
)

error_other = Schema(
    {"error_type": nonempty_str, "error_traceback": nonempty_str},
    required=True,
    extra=False,
)

success_pull = Schema(
    {
        "branch": nonempty_str,
        "tag": nonempty_str,
        "url": {
            "readonly": Url(),  # pylint: disable=no-value-for-parameter
            "readwrite": Url(),  # pylint: disable=no-value-for-parameter
        },
    },
    required=True,
    extra=False,
)

success_adjust = success_pull

success_pull_adjust = Schema(
    {
        "branch": nonempty_str,
        "tag": nonempty_str,
        "url": {
            "readonly": Url(),  # pylint: disable=no-value-for-parameter
            "readwrite": Url(),  # pylint: disable=no-value-for-parameter
        },
        "pull": success_pull,
    },
    required=True,
    extra=False,
)

#
# Server configuration
#

server_config_raw = {
    "log": {"path": nonempty_str, "level": Any(*logging._nameToLevel.keys())},
    "bind": {"address": Any(nonempty_str, None), "port": port_num},
    "adjust_provider": {"type": Any(nonempty_str, None), "params": {Extra: object}},
    "repo_provider": {
        "type": Any(*repo.provider_types.keys()),
        "params": {Extra: object},
    },
}
server_config = Schema(server_config_raw, required=True, extra=False)
