# flake8: noqa
import io
import logging
import os
import zipfile

from repour import asutil, exception

logger = logging.getLogger(__name__)

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

stdout_options = asutil.process_stdout_options
stderr_options = asutil.process_stderr_options

# This provider MAY be "extended" by other providers.
def get_process_provider(
    execution_name,
    cmd,
    get_result_data=None,
    log_context_option=None,
    send_log=False,
    results_file=None,
):
    async def get_result_data_default(work_dir):
        return {}

    get_result_data = (
        get_result_data if get_result_data is not None else get_result_data_default
    )

    async def adjust(
        repo_dir, extra_adjust_parameters, adjust_result, dir_results=None, env=None
    ):
        """
        dir_results is used to define where to get the results data from. By default it is 'repo_dir'
        """
        # TODO: Why 'adjust_result' is ignored?
        nonlocal execution_name
        logger.info(
            'Executing "{execution_name}" using (sub)process adjust provider as: '.format(
                **locals()
            )
            + " ".join(cmd)
        )
        log_executable_info(cmd)
        filled_cmd = [
            p.format(repo_dir=repo_dir) if p.startswith("{repo_dir}") else p
            for p in cmd
        ]

        stdout = None
        try:
            stdout = await expect_ok(
                cmd=filled_cmd,
                desc="Adjust subprocess failed.",
                cwd=repo_dir,
                env=env,
                stdout=stdout_options["lines"]
                if send_log
                else stdout_options["ignore"],
                stderr=stderr_options["stdout"]
                if send_log
                else stderr_options["log_on_error"],
                live_log=send_log,
            )
        except exception.CommandError as e:
            logger.error(
                'Adjust subprocess failed, exited code "{e.exit_code}"'.format(
                    **locals()
                )
            )
            raise

        logger.info("Adjust subprocess exited OK!")

        dir_where_results_are = repo_dir
        if dir_results:
            dir_where_results_are = dir_results

        adjust_result_data = {}

        adjust_result_data["adjustType"] = execution_name
        adjust_result_data["resultData"] = await get_result_data(
            dir_results, extra_adjust_parameters, results_file=results_file
        )

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
                logger.info(
                    "Adjust provider jar: {basename}, {title}, {version}".format(
                        **locals()
                    )
                )
