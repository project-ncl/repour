import asyncio
import logging
import os
import shutil
import tempfile
import urllib.parse

import aiohttp

from . import exception

logger = logging.getLogger(__name__)
subprocess_logger = logging.getLogger(__name__ + ".stderr")

def _find_filename(url, resp):
    # Filename should be url basename, or Content-Disposition header if it exists
    if aiohttp.hdrs.CONTENT_DISPOSITION in resp.headers:
        cd_params = aiohttp.multipart.parse_content_disposition(resp.headers[aiohttp.hdrs.CONTENT_DISPOSITION])[1]
        cd_filename = aiohttp.multipart.content_disposition_filename(cd_params)
    else:
        cd_filename = None

    if cd_filename is None:
        return os.path.basename(urllib.parse.urlparse(url).path)
    else:
        return cd_filename

@asyncio.coroutine
def download(url, stream):
    loop = asyncio.get_event_loop()

    resp = yield from aiohttp.request("get", url)
    try:
        while True:
            chunk = yield from resp.content.read(4096)
            if not chunk:
                break
            yield from loop.run_in_executor(None, stream.write, chunk)
    except:
        resp.close(True)
        raise
    else:
        resp.close()

    filename = _find_filename(url, resp)

    if hasattr(stream, "flush"):
        yield from loop.run_in_executor(None, stream.flush)
    if hasattr(stream, "sync"):
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

def _convert_bytes(b, mode):
    if mode == "text":
        return b.decode("utf-8")
    elif mode == "lines":
        return [l for l in b.decode("utf-8").split("\n") if l != ""]
    elif mode == "single":
        return b.decode("utf-8").split("\n", 1)[0]
    elif mode == "data":
        return b
    else:
        return None

def expect_ok_closure(exc_type=exception.CommandError):
    @asyncio.coroutine
    def expect_ok(cmd, desc="", env=None, stdout=None, stderr="log_on_error", cwd=None):
        if env is None:
            sub_env = None
        else:
            # Only partially override the existing environment
            sub_env = os.environ.copy()
            sub_env.update(env)

        p = yield from asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=None if stdout == "send" else asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if stderr == "stdout" else asyncio.subprocess.PIPE,
            env=sub_env,
            cwd=cwd
        )

        stdout_data, stderr_data = yield from p.communicate()

        stderr_text = "" if stderr_data is None else stderr_data.decode("utf-8")

        if stderr_text != "" and (stderr == "log" or (stderr == "log_on_error" and p.returncode != 0)):
            for line in stderr_text.split("\n"):
                if line != "":
                    subprocess_logger.error(line)

        if not p.returncode == 0:
            raise exc_type(
                desc=desc,
                cmd=cmd,
                exit_code=p.returncode,
                stdout="" if stdout_data is None else stdout_data.decode("utf-8"),
                stderr=stderr_text,
            )
        else:
            if stdout == "send":
                return None
            else:
                return _convert_bytes(stdout_data, stdout)

    return expect_ok
