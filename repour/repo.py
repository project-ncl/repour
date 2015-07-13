import asyncio
import base64
import hashlib
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

    def es(o):
        return json.dumps(obj=o, ensure_ascii=False)

    def md5(*args):
        h = hashlib.md5()
        h.update(":".join(args).encode("utf-8"))
        return h.hexdigest()

    realm = ""
    ncount = 0
    nonce = ""
    def authorization_value(method, path):
        nonlocal ncount
        ncount += 1
        cnonce = base64.b64encode(os.urandom(16)).decode("utf-8")

        qop = "auth"

        ha1 = md5(username, realm, password)
        ha2 = md5(method, path)
        response = md5(ha1, nonce, ncount, cnonce, qop, ha2)

        parts = {
            "username": username,
            "realm": realm,
            "nonce": nonce,
            "uri": path,
            "qop": qop,
            "nc": ncount,
            "cnonce": cnonce,
            "response": response,
        }
        return "Digest " + ",".join('{}={}'.format(k,es(v)) for k,v in parts.items())

    @asyncio.coroutine
    def get_url(repo_name, tried_auth=False):
        nonlocal realm, ncount, nonce

        encoded_repo_name = urllib.parse.quote(repo_name)
        auth_url = api_url + "/a/projects/" + encoded_repo_name
        auth_path = urllib.parse.urlparse(auth_url).path

        resp = yield from session.put(
            auth_url,
            headers={
                "If-None-Match": "*",
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json",
                "Authorization": authorization_value("PUT", auth_path),
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
        if resp.status in [201, 412]:
            return api_url + "/projects/" + encoded_repo_name

        # (Re)authenticate
        elif not tried_auth and resp.status == 401:
            auth = resp.headers["WWW-Authenticate"]

            # Strip "Digest "
            raw_params = auth[7:].split(",")
            params = {}
            for p in raw_params:
                # Seperate k="v"
                k, v = p.split("=", 1)
                # Remove quotes from value
                params[k] = v[1:-1]

            realm = params["realm"]
            nonce = params["nonce"]
            ncount = 0

            # Try request once more before failing
            yield from get_url(repo_name, True)

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
