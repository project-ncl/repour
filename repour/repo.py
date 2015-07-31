import asyncio
import collections
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

@asyncio.coroutine
def _retry_with_auth(action, auth, reauth_status=401, retry_count=1):
    resp = None
    while resp is None or retry_count > 0:
        resp = yield from action()
        if resp.status == reauth_status:
            retry_count -= 1
            yield from auth()
        else:
            break
    else:
        raise exception.RepoError("Could not authenticate, status {}".format(resp.status))

    return resp

expect_ok = asutil.expect_ok_closure(exception.RepoCommandError)

RepoUrls = collections.namedtuple("RepoUrls", ["readwrite", "readonly"])

#
# Repo operations
#

def repo_gerrit(api_url, username, password, new_repo_owners):
    session = aiohttp.ClientSession() #pylint: disable=no-member

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
    def get_url(repo_name, create=True, tried_auth=False):
        nonlocal realm, ncount, nonce

        encoded_repo_name = urllib.parse.quote(repo_name)
        auth_url = api_url + "/a/projects/" + encoded_repo_name
        auth_path = urllib.parse.urlparse(auth_url).path

        clone_url = api_url + "/projects/" + encoded_repo_name
        if not create:
            return RepoUrls(
                readwrite=clone_url,
                readonly=TODO,
            )

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
            return RepoUrls(
                readwrite=clone_url,
                readonly=TODO,
            )

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

def repo_gitlab(root_url, ssh_root_url, group, username, password):
    api_url = root_url + "/api/v3"
    auth_url = root_url + "/oauth/token"

    session = aiohttp.ClientSession() #pylint: disable=no-member

    access_token = ""
    @asyncio.coroutine
    def new_token():
        nonlocal access_token

        resp = yield from session.post(
            auth_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data=urllib.parse.urlencode({
                "grant_type": "password",
                "username": username,
                "password": password,
            }).encode("utf-8"),
        )
        if resp.status // 100 != 2:
            raise exception.RepoError("Unable to authenticate, status {}".format(resp.status))

        data = yield from resp.json()
        access_token = data["access_token"]

    @asyncio.coroutine
    def get_url(repo_name, create=True):
        repo_url_suffix = "/{}/{}.git".format(group["name"], urllib.parse.quote(repo_name))
        repo_url = RepoUrls(
            readwrite=root_url + repo_url_suffix,
            readonly=ssh_root_url + repo_url_suffix,
        )
        if not create:
            return repo_url

        @asyncio.coroutine
        def create_repo():
            resp = yield from session.post(
                api_url + "/projects",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "Authorization": "Bearer " + access_token,
                },
                data=urllib.parse.urlencode({
                    "name": repo_name,
                    "namespace_id": group["id"],
                    "visibility_level": 20,
                }).encode("utf-8"),
            )
            return resp

        resp = yield from _retry_with_auth(
            action=create_repo,
            auth=new_token,
        )

        if resp.status == 400:
            try:
                data = yield from resp.json()
            except Exception:
                data = {}
            if "has already been taken" in data.get("message", {}).get("name", []):
                # Repo already exists
                return repo_url
            raise exception.RepoError("Project creation unsuccessful, status {}".format(resp.status))
        elif resp.status // 100 != 2:
            raise exception.RepoError("Project creation unsuccessful, status {}".format(resp.status))

    return get_url

def repo_local(root_url):
    root_path = urllib.parse.urlparse(root_url).path
    @asyncio.coroutine
    def get_url(repo_name, create=True):
        repo_path = os.path.join(root_path, repo_name)
        _repo_url = urllib.parse.ParseResult(
            scheme="file",
            netloc=None,
            path=repo_path,
            params=None,
            query=None,
            fragment=None,
        ).geturl()
        repo_url = RepoUrls(
            readwrite=_repo_url,
            readonly=_repo_url,
        )

        if not create:
            return repo_url

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
