import asyncio
import os
import shutil
import tempfile
import urllib.parse

import aiohttp

from . import exception

@asyncio.coroutine
def download(url, stream):
    loop = asyncio.get_event_loop()

    session = aiohttp.ClientSession(loop=loop)
    resp = yield from session.request("get", url)
    while True:
        chunk = yield from resp.content.read(4096)
        if not chunk:
            break
        yield from loop.run_in_executor(None, stream.write, chunk)

    # Filename should be url basename, or Content-Disposition header if it exists
    cd_params = aiohttp.multipart.parse_content_disposition(resp.headers[aiohttp.hdrs.CONTENT_DISPOSITION])[1]
    cd_filename = aiohttp.multipart.content_disposition_filename(cd_params)
    if cd_filename is None:
        filename = os.path.basename(urllib.parse.urlparse(url).path)
    else:
        filename = cd_filename

    yield from loop.run_in_executor(None, stream.sync)

    return filename

@asyncio.coroutine
def rmtree(dir_path, ignore_errors=False, loop=None):
    loop = asyncio.get_event_loop() if loop is None else loop
    yield from loop.run_in_executor(None, lambda: shutil.rmtree(dir_path, ignore_errors))

class TemporaryDirectory(object):
    def __init__(self, suffix="", prefix="tmp", loop=None):
        self.suffix = suffix
        self.prefix = prefix
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self.name = None

    def __enter__(self):
        self.name = tempfile.mkdtemp(self.suffix, self.prefix)
        return self.name

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.loop.create_task(rmtree(self.name, ignore_errors=True, loop=self.loop))

def expect_ok_closure(exc_type=exception.CommandError):
    @asyncio.coroutine
    def expect_ok(cmd, desc=""):
        p = yield from asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        yield from p.wait()
        if not p.returncode == 0:
            raise exc_type(
                desc=desc,
                cmd=cmd,
                exit_code=p.returncode,
            )
    return expect_ok
