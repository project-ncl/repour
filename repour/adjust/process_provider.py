import asyncio
import io
import logging
import os
import zipfile

from .. import asutil
from .. import exception

logger = logging.getLogger(__name__)

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

stdout_options = asutil.process_stdout_options
stderr_options = asutil.process_stderr_options

# This provider MAY be "extended" by other providers.
def get_process_provider(execution_name, cmd, get_result_data=None, log_context_option=None, send_log=False):
    @asyncio.coroutine
    def get_result_data_default(work_dir):
        return {}

    get_result_data = get_result_data if get_result_data is not None else get_result_data_default

    @asyncio.coroutine
    def adjust(repo_dir, extra_adjust_parameters, adjust_result):
        nonlocal execution_name
        logger.info('Executing "{execution_name}" using (sub)process adjust provider as "{cmd}".'.format(**locals()))
        log_executable_info(cmd)
        filled_cmd = [p.format(repo_dir=repo_dir) if p.startswith("{repo_dir}") else p for p in cmd]

        # log_context = getattr(asyncio.Task.current_task(), "log_context", None)
        # if log_context_option is None:
        #     if log_context is None:
        #         env = None
        #     else:
        #         env = {
        #             "LOG_CONTEXT": asyncio.Task.current_task().log_context,
        #         }
        # else:
        #     env = None
        #     if log_context is not None:
        #         filled_cmd.append(log_context_option)
        #         filled_cmd.append(log_context)
        env = None
        stdout = None
        try:
            stdout = yield from expect_ok(
                cmd=filled_cmd,
                desc="Adjust subprocess failed.",
                cwd=repo_dir,
                env=env,
                stdout=stdout_options["lines"] if send_log else stdout_options["ignore"],
                stderr=stderr_options["stdout"] if send_log else stderr_options["log_on_error"],
            )
        except exception.CommandError as e:
            logger.error('Adjust subprocess failed, exited code "{e.exit_code}"'.format(**locals()))
            raise

        logger.info("Adjust subprocess exited OK!")

        adjust_result_data = {}
        # TODO adjust_result_data["stdout"] = stdout
        logger.info("PME output:")
        logger.info(stdout)
        adjust_result_data["adjustType"] = execution_name
        adjust_result_data["resultData"] = yield from get_result_data(repo_dir)
        return adjust_result_data

    return adjust


#
# Utility
#

def log_executable_info(cmd):
    first = True
    for c in cmd:
        if c.endswith(".jar"):
            manifest = {}
            try:
                with zipfile.ZipFile(c) as z:
                    with z.open("META-INF/MANIFEST.MF") as bf:
                        f = io.TextIOWrapper(bf)
                        raw_lines = f.readlines()
                        previous_k = None
                        for line in raw_lines:
                            if line.startswith(" "):
                                assert previous_k is not None
                                manifest[previous_k] += line.strip()
                            elif line == "\n":
                                pass
                            else:
                                k, v = line.rstrip().split(":", 1)
                                manifest[k] = v.lstrip()
                                previous_k = k
            except FileNotFoundError:
                pass
            except KeyError:
                pass
            else:
                basename = os.path.basename(c)
                title = manifest.get("Implementation-Title", "Unknown")
                version = manifest.get("Implementation-Version", "Unknown")
                logger.info("Adjust provider jar: {basename}, {title}, {version}".format(**locals()))
