# flake8: noqa
import asyncio
import logging
import os
import re
import shutil
import tempfile
import urllib.parse

import aiohttp

from repour import exception

logger = logging.getLogger(__name__)
subprocess_logger = logging.getLogger(__name__ + ".stderr")


def _find_filename(url, resp):
    # Filename should be url basename, or Content-Disposition header if it exists
    if aiohttp.hdrs.CONTENT_DISPOSITION in resp.headers:
        cd_params = aiohttp.multipart.parse_content_disposition(
            resp.headers[aiohttp.hdrs.CONTENT_DISPOSITION]
        )[1]
        cd_filename = aiohttp.multipart.content_disposition_filename(cd_params)
    else:
        cd_filename = None

    if cd_filename is None:
        return os.path.basename(urllib.parse.urlparse(url).path)
    else:
        return cd_filename


async def download(url, stream):
    loop = asyncio.get_event_loop()

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:

            try:
                while True:
                    chunk = await resp.content.read(4096)
                    if not chunk:
                        break
                    await loop.run_in_executor(None, stream.write, chunk)
            except:
                raise

    filename = _find_filename(url, resp)

    if hasattr(stream, "flush"):
        await loop.run_in_executor(None, stream.flush)
    if hasattr(stream, "sync"):
        await loop.run_in_executor(None, stream.sync)

    return filename


async def rmtree(dir_path, ignore_errors=False, loop=None):
    loop = asyncio.get_event_loop() if loop is None else loop
    await loop.run_in_executor(None, lambda: shutil.rmtree(dir_path, ignore_errors))


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
    "capture": "capture",  # ???
    "text": "text",  # see _convert_bytes
    "lines": "lines",
    "single": "single",
    "data": "data",
}

process_stderr_options = {
    "log": "log",
    "log_on_error": "log_on_error",
    "stdout": "stdout",
}


def expect_ok_closure(exc_type=exception.CommandError):
    """
    Uses a custom logger name ('process') when printing live logs to the logging infrastructure.
    """
    # Special logger name used to print custom context in the output
    logger_process = logging.getLogger("process")

    async def print_live_log(process):
        """
        Known issues: it doesn't really process stderr, it assumes stderr is redirected
                      to stdout
        """
        BYTES_TO_READ = 5000

        stdout_data_ary = []
        stderr_text = ""

        while True:

            # Try to read up to BYTES_TO_READ to read in batch rather than reading line by line
            # if the length of data read is exactly BYTES_TO_READ, that probably means the data read didn't finish at the end of a line
            # So read some more to guarantee all the data read ends at the end of a line
            data = await process.stdout.read(BYTES_TO_READ)
            if len(data) == BYTES_TO_READ:
                # Sleep to give a chance for other unrelated async tasks to run. In theory we shouldn't need it, but in practice this
                # loop tends to get all the attention of the event loop and prevents other unrelated async tasks to run. The sleep prevents this
                await asyncio.sleep(0.1)
                # data_second necessary to make the entire 'data' are strings of complete lines. We cannot guarantee that the 1000th byte ends with "\n"
                data_second = await process.stdout.readline()
                data += data_second

            decoded = data.decode()

            if decoded == "":
                # that means we reached EOF and process stopped
                break
            else:
                # decoded contains multiple lines in a string
                decoded_list = decoded.splitlines()
                for item in decoded_list:
                    logger_process.info(item)
                stdout_data_ary.extend(decoded_list)

        stdout_text = "\n".join(stdout_data_ary)
        return stdout_text, stderr_text

    async def expect_ok(
        cmd,
        desc="",
        env=None,
        stdout=None,
        stderr="log_on_error",
        cwd=None,
        live_log=False,
        print_cmd=False,
    ):
        """
        If stderr is set to 'log_on_error', the text in stderr will be logged as ERROR if the cmd return code is not zero
        If stderr is set to 'log_on_error_as_info', the text in stderr will be logged as a INFO if the cmd return code is not zero
        If stderr is set to 'log', the text in stderr will be logged as an error irrespective of the cmd return code value
        """

        # load the system's env vars
        sub_env = os.environ.copy()

        if env:
            # Only partially override the existing environment
            sub_env.update(env)

        if print_cmd:
            logger.info("Running command: {}".format(cmd))

        p = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=None
            if stdout == process_stdout_options["ignore"]
            else asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
            if stderr == process_stderr_options["stdout"]
            else asyncio.subprocess.PIPE,
            env=sub_env,
            cwd=cwd,
            limit=100 * 1024 * 1024
        )

        if live_log:
            stdout_text, stderr_text = await print_live_log(p)
            await p.wait()
        else:
            stdout_data, stderr_data = await p.communicate()
            stderr_text = (
                "" if stderr_data is None else _convert_bytes(stderr_data, "text")
            )
            stdout_text = (
                "" if stdout_data is None else _convert_bytes(stdout_data, "text")
            )

        if stderr_text != "":
            if stderr == "log_on_error" and p.returncode != 0:
                subprocess_logger.error(stderr_text)
            elif stderr == "log_on_error_as_info" and p.returncode != 0:
                subprocess_logger.info(stderr_text)
            elif stderr == "log":
                subprocess_logger.error(stderr_text)

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
                    return stdout_text.split("\n")
                else:
                    return _convert_bytes(stdout_data, stdout)

    return expect_ok


def add_username_url(url, username):
    """Given a url, add username to the url if not already in url

    If username is empty (None or "") or the url is in SCP-like format, do nothing, return url as is

    returns: :str: url with username
    """

    # If username is None or empty or url is in SCP-like format, do nothing
    if not username or url.startswith("git@"):
        return url

    parsed = urllib.parse.urlsplit(url)

    if parsed.username:
        # username info already in url, all good!
        return url
    else:
        parsed_list = list(parsed)
        # first item is the protocol, second is the url name
        url_part = parsed_list[1]
        parsed_list[1] = username + "@" + url_part

        return urllib.parse.urlunsplit(parsed_list)


def safe_remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass


def list_urls_from_string(text):
    """
    From: https://stackoverflow.com/a/48769624/2907906
    Modified to require the protocol (http:// or https://) to be present

    It'll return a list of urls present in the string
    """
    return re.findall("(?:(?:https?):\\/\\/)[\\w/\\-?=%.]+\\.[\\w/\\-?=%.]+", text)


def list_non_origin_urls_from_string(origin_url, text):
    """
    Given a string, list all the urls that do not end with 'origin_url'.
    """

    result = []
    urls = list_urls_from_string(text)

    for url in urls:

        url_parsed = urllib.parse.urlparse(url)

        if not url_parsed.netloc.endswith(origin_url):
            result.append(url)

    return result
