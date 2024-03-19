import asyncio
import hashlib
import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class LogMetadata:
    """
    Data class to hold information on the metadata to upload
    """

    end_time: str = ""
    logger_name: str = ""
    tag: str = ""
    process_context: str = ""
    process_context_variant: str = "0"
    tmp: str = ""
    request_context: str = ""
    user_id: str = ""
    expires: str = ""
    trace_id: str = ""
    span_id: str = ""
    traceparent: str = ""


async def send(url, filename, log_metadata: LogMetadata, access_token):
    """
    Upload final log file to Bifrost. Inspired from: https://github.com/project-ncl/bifrost-upload-client
    """
    backoff = 1
    max_attempts = 9

    while True:
        async with aiohttp.ClientSession() as session:
            with aiohttp.MultipartWriter("form-data") as mp:
                __add_file(mp, filename, "logfile")

                # Data part in multipart/form
                md5sum = __md5sum_of_file(filename)

                __add_part(mp, "md5sum", md5sum)
                __add_part(mp, "endTime", log_metadata.end_time)
                __add_part(mp, "loggerName", log_metadata.logger_name)
                __add_part(mp, "tag", log_metadata.tag)

                # HTTP headers
                headers = {
                    "Authorization": "Bearer " + access_token,
                    "log-process-context": log_metadata.process_context,
                    "process-context-variant": log_metadata.process_context_variant,
                    "log-tmp": log_metadata.tmp,
                    "log-request-context": log_metadata.request_context,
                    "log-user-id": log_metadata.user_id,
                    "log-expires": log_metadata.expires,
                    "trace-id": log_metadata.trace_id,
                    "span-id": log_metadata.span_id,
                    "traceparent": log_metadata.traceparent,
                }

                resp = await session.post(
                    url + "/upload/final-log", data=mp, headers=headers, compress=True
                )

                if resp is not None and resp.status // 100 == 2:
                    return resp
                else:
                    logger.info(
                        "Unable to send logs to bifrost, status {resp.status}, text {resp.text}, attempt {backoff}/{max_attempts}".format(
                            **locals()
                        )
                    )
                    sleep_period = 2**backoff
                    logger.debug("Sleeping for {sleep_period}".format(**locals()))
                    await asyncio.sleep(sleep_period)

                    backoff += 1

                    if backoff > max_attempts:
                        logger.error(
                            "Giving up on callback after {max_attempts} attempts".format(
                                **locals()
                            )
                        )
                        raise Exception(
                            "Couldn't send logs to Bifrost:: HTTP status: {} with text: {}".format(
                                resp.status, resp.text
                            )
                        )


def __add_part(multipart_writer, name, value):
    part = multipart_writer.append(value)
    part.set_content_disposition("form-data", name=name)


def __add_file(multipart_writer, filename_path, filename_for_upload=None):
    """
    Specify filename_for_upload if you want to override the filename string to send with another name
    """
    part = multipart_writer.append(open(filename_path, "rb"))

    part.headers["Content-Type"] = "application/octet-stream"

    if filename_for_upload:
        part.set_content_disposition("form-data", name=filename_for_upload)
    else:
        part.set_content_disposition("form-data", name=filename_path)


def __md5sum_of_file(filename):
    """
    Use this helper method to calculate the md5 of a file.

    Rather than loading the whole filename into memory and calculating the md5,
    instead we load it in chunks to reduce memory usage.
    """

    buf_size = 65536  # lets read stuff in 64kb chunks!
    md5 = hashlib.md5()

    with open(filename, "rb") as f:
        while True:
            data = f.read(buf_size)
            if not data:
                break
            md5.update(data)

    return md5.hexdigest()
