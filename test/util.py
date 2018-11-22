import os
import subprocess
import tempfile

import aiohttp.web

import repour.repo

class TemporaryGitDirectory(tempfile.TemporaryDirectory):
    def __init__(self, bare=False, origin=None, ro_url=None, ref=None):
        super().__init__()
        self.bare = bare
        self.origin = origin
        self.ro_url = ro_url
        self.ref = ref

    def __enter__(self):
        if self.ref is None:
            cmd = ["git", "init"]
            if self.bare:
                cmd.append("--bare")
            cmd.append(self.name)
            quiet_check_call(cmd)

            if self.origin is not None:
                quiet_check_call(["git", "remote", "add", "origin", "file://" + self.origin], cwd=self.name)
        else:
            quiet_check_call(["git", "clone", "--branch", self.ref, "--", "file://" + self.origin, self.name])

        quiet_check_call(["git", "config", "--local", "user.name", "Repour"], cwd=self.name)
        quiet_check_call(["git", "config", "--local", "user.email", "<>"], cwd=self.name)

        if self.ro_url is not None:
            return repour.repo.RepoUrls(readonly=self.ro_url, readwrite=self.name)
        else:
            return self.name

class TemporaryHgDirectory(tempfile.TemporaryDirectory):
    def __init__(self, add_commit=True):
        super().__init__()
        self.add_commit = add_commit

    def __enter__(self):
        cmd = ["hg", "init", self.name]
        quiet_check_call(cmd)

        if self.add_commit:
            with open(os.path.join(self.name, "hello.txt"), "w") as f:
                f.write("Hello!\n")
            quiet_check_call(["hg", "--cwd", self.name, "add", "hello.txt"])
            quiet_check_call(["hg", "--cwd", self.name, "commit", "-m", "A friendly commit"])

        return self.name

def quiet_check_call(cmd, cwd=None):
    if cwd is None:
        return subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        return subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=cwd)

def setup_http(cls, loop, routes):
    app = aiohttp.web.Application(loop=loop)

    for route in routes:
        app.router.add_route(*route)

    host = "localhost"
    port = 51854
    cls.url = "http://{host}:{port}".format(**locals())
    cls.handler = app.make_handler()
    cls.server = loop.run_until_complete(loop.create_server(cls.handler, host, port))

def teardown_http(cls, loop):
    cls.server.close()
    loop.run_until_complete(cls.server.wait_closed())

def http_write_handler(stream):
    async def handler(request):
        resp = aiohttp.web.StreamResponse()
        await resp.prepare(request)

        stream.seek(0)
        while True:
            buf = stream.read(4096)
            if not buf:
                break
            await resp.write(buf)
            await resp.drain()
        await resp.write_eof()

        return resp

    return handler
