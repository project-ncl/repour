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
        resp.close()
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

# TODO values are for backwards comp., replace with enum
process_stdout_options = {
    "ignore": "send",
    "capture": "capture", # ???
    "text":"text", # see _convert_bytes
    "lines":"lines",
    "single":"single",
    "data":"data",
}

process_stderr_options = {
    "log": "log",
    "log_on_error": "log_on_error",
    "stdout": "stdout"
}

def expect_ok_closure(exc_type=exception.CommandError):
    @asyncio.coroutine
    def print_live_log(process):
        """
        Known issues: it doesn't really process stderr, it assumes stderr is redirected
                      to stdout
        """
        stdout_data_ary = []
        stderr_text = ""

        while True:
            data = yield from process.stdout.readline()
            decoded = data.decode()
            if decoded == '':
                # that means we reached EOF and process stopped
                break
            else:
                decoded_stripped = decoded.strip()
                logger.info(decoded_stripped)
                stdout_data_ary.append(decoded_stripped)

        stdout_text = '\n'.join(stdout_data_ary)
        return stdout_text, stderr_text

    @asyncio.coroutine
    def expect_ok(cmd, desc="", env=None, stdout=None, stderr="log_on_error", cwd=None, live_log=False):
        if env is None:
            sub_env = None
        else:
            # Only partially override the existing environment
            sub_env = os.environ.copy()
            sub_env.update(env)

        p = yield from asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=None if stdout == process_stdout_options["ignore"] else asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if stderr == process_stderr_options["stdout"] else asyncio.subprocess.PIPE,
            env=sub_env,
            cwd=cwd,
            limit=100*1024*1024
        )

        if live_log:
            stdout_text, stderr_text = yield from print_live_log(p)
            yield from p.wait()
        else:
            stdout_data, stderr_data = yield from p.communicate()
            stderr_text = "" if stderr_data is None else _convert_bytes(stderr_data, "text")
            stdout_text = "" if stdout_data is None else _convert_bytes(stdout_data, "text")

        if stderr_text != "" and (stderr == "log" or (stderr == "log_on_error" and p.returncode != 0)):
            for line in stderr_text.split("\n"):
                if line != "":
                    subprocess_logger.error(line)

        if not p.returncode == 0:
            raise exc_type(
                desc=desc,
                cmd=cmd,
                exit_code=p.returncode,
                stdout=stdout_text,
                stderr=stderr_text,
            )
        else:
            if stdout == "send":
                return None
            else:
                if live_log:
                    return stdout_text.split('\n')
                else:
                    return _convert_bytes(stdout_data, stdout)

    return expect_ok


def add_username_url(url, username):
    """ Given a url, add username to the url if not already in url

    returns: :str: url with username
    """
    parsed = urllib.parse.urlsplit(url)

    if parsed.username:
        # username info already in url, all good!
        return url
    else:
        parsed_list = list(parsed)
        # first item is the protocol, second is the url name
        url_part = parsed_list[1]
        parsed_list[1] = username + '@' + url_part

        return urllib.parse.urlunsplit(parsed_list)
