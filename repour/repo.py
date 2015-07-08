import asyncio
import logging
import os
import urllib.parse

from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.RepoCommandError)

#
# Repo operations
#

def repo_gitlab(api_url):
    @asyncio.coroutine
    def get_url(repo_name):
        raise Exception("Not implemented")
    return get_url

def repo_local(root_url):
    root_path = urllib.parse.urlparse(root_url).path
    @asyncio.coroutine
    def get_url(repo_name):
        repo_path = os.path.join(root_path, repo_name)
        repo_url = urllib.parse.ParseResult(
            scheme="file",
            netloc=None,
            path=repo_path,
            params=None,
            query=None,
            fragment=None,
        ).geturl()

        if os.path.exists(repo_path):
            logger.debug("Returning existing local repo at {repo_path}".format(**locals()))
        else:
            yield from expect_ok(
                cmd=["git", "init", "--bare", repo_path],
                desc="Could not create local repo with git",
            )
            logger.info("Created new local repo at {repo_path}".format(**locals()))

        return repo_url
    return get_url

#
# Supported
#

provider_types = {
    "gitlab": repo_gitlab,
    "local": repo_local,
}
