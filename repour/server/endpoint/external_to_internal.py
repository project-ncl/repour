# flake8: noqa
import re
from urllib.parse import urlparse

from prometheus_async.aio import time
from prometheus_client import Histogram, Summary

from ...config import config

REQ_TIME = Summary(
    "external_to_internal_req_time", "time spent with external_to_internal endpoint"
)
REQ_HISTOGRAM_TIME = Histogram(
    "external_to_internal_req_histogram", "Histogram for external_to_internal endpoint"
)


@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def translate(external_to_internal_spec, repo_provider):

    external_url = external_to_internal_spec["external_url"]

    internal_url = await translate_external_to_internal(external_url)

    result = {"external_url": external_url, "internal_url": internal_url}

    return result


async def translate_external_to_internal(external_git_url):
    """ Logic from original maitai code to do this: found in GitUrlParser.java#generateInternalGitRepoName """

    c = await config.get_configuration()
    gerrit_server = c.get("git_url_internal_template", None)

    if gerrit_server is None:
        raise Exception("git_url_internal_template not specified in the Repour config!")
    elif not gerrit_server.endswith("/"):
        gerrit_server = gerrit_server + "/"

    result = urlparse(external_git_url)

    scheme = result.scheme
    path = result.path

    acceptable_schemes = ["https", "http", "git", "git+ssh", "ssh"]

    if scheme == "":
        raise Exception("Scheme in url is empty! Error!")

    if scheme not in acceptable_schemes:
        raise Exception("Scheme '{0}' not accepted!'".format(scheme))

    path_parts = path.split("/")

    repository = None

    if path_parts[-1]:
        repository = re.sub(r"\.git$", "", path_parts[-1])

    organization = None

    # if organization name is 'gerrit', don't use it then
    if len(path_parts) > 1 and path_parts[-2] != "gerrit" and path_parts[-2]:
        organization = path_parts[-2]

    if organization and repository:
        repo_name = organization + "/" + repository
    elif repository:
        repo_name = repository
    else:
        raise Exception("Could not translate the URL: No repository specified!")

    return gerrit_server + repo_name + ".git"
