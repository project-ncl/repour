import asyncio
import json
import logging
import os
import urllib.parse

import aiohttp

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

def repo_gerrit(api_url, username, password, new_repo_owners):
    session = aiohttp.ClientSession()

    @asyncio.coroutine
    def get_url(repo_name):
        encoded_repo_name = urllib.parse.quote(repo_name)
        auth_url = api_url + "/a/projects/" + encoded_repo_name

        # Trigger WWW-Authenticate
        resp = yield from session.put(auth_url)
        if resp.status == 401:
            resp.headers["WWW-Authenticate"] # TODO
        else:
            raise exception.RepoError("Unable to authenticate, status {}".format(resp.status))

        resp = yield from session.put(
            auth_url,
            headers={
                "If-None-Match": "*",
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json",
            },
            data=json.dumps(
                obj={
                    "name": repo_name,
                    "description": "Flattened repository for {}".format(repo_name),
                    "submit_type": "FAST_FORWARD_ONLY",
                    "owners": new_repo_owners,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        # Project was created or already exists
        if resp.status in [201,412]:
            return api_url + "/projects/" + encoded_repo_name
        else:
            raise exception.RepoError("Project creation unsuccessful, status {}".format(resp.status))

    return get_url

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
    "gerrit": repo_gerrit,
    "gitlab": repo_gitlab,
    "local": repo_local,
}
