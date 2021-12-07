import asyncio
import calendar
import logging
import pylru
import os
import time

from repour import asutil

SHARED_PATH_PREFOLDER = os.environ.get("SHARED_FOLDER", "/tmp")
CALLBACK_LOGS_PATH = os.path.join(SHARED_PATH_PREFOLDER, "repour-logs-callback")

logger = logging.getLogger(__name__)


def get_callback_log_path(callback_id):
    return os.path.join(CALLBACK_LOGS_PATH, callback_id + ".log")


def has_event_loop():
    """ If another thread (e.g kafka) is writing a log, the file_callback_log will be invoked inside that thread. In that case,
    there is no event loop in that other thread and we need to know this
    """
    try:
        asyncio.get_event_loop()
        return True
    except RuntimeError:
        return False


class FileCallbackHandler(logging.StreamHandler):
    """
    Handler that logs into {directory}/{callback_id}.log
    """

    def __init__(
        self, directory=CALLBACK_LOGS_PATH, mode="a", encoding=None, delay=None
    ):
        if os.path.exists(directory):
            if not os.path.isdir(directory):
                raise Exception(directory + " is not a directory! Can't log there")
        else:
            os.makedirs(directory)

        self.filename = directory
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        self.cache_file_handler = pylru.lrucache(20, close_file_handler)
        logging.Handler.__init__(self)

    def emit(self, record):
        try:
            if has_event_loop():
                task = asyncio.current_task()
            else:
                task = None

            if task is not None:
                callback_id = getattr(task, "callback_id", None)
                if callback_id is not None:
                    self.stream = self._open_callback_file(callback_id)
                    logging.StreamHandler.emit(self, record)

                    # need to flush to make sure every reader sees the change
                    self.stream.flush()
        except RuntimeError:
            self.handleError(record)

    def _open_callback_file(self, callback_id):
        path = get_callback_log_path(callback_id)

        # Cache the most recently file handlers. If not in cache, then create one.
        # Done because creating a new file handler on every `emit` is very costly
        if callback_id not in self.cache_file_handler:
            self.cache_file_handler[callback_id] = open(
                path, self.mode, encoding=self.encoding
            )

        return self.cache_file_handler[callback_id]


async def setup_clean_old_logfiles():
    """
    We cleanup old log files that haven't been written to for the past 2 days
    """
    while True:
        for filename in os.listdir(CALLBACK_LOGS_PATH):
            path = os.path.join(CALLBACK_LOGS_PATH, filename)

            epoch_filename = int(os.stat(path).st_ctime)
            current_epoch = calendar.timegm(time.gmtime())

            # 172800 seconds = 2 days
            if current_epoch - epoch_filename > 172800:
                logger.info("Removing old logfile: " + path)
                asutil.safe_remove_file(path)

        # Run every hour
        await asyncio.sleep(3600)


def close_file_handler(key, value):
    """
    Close the file handler once it is evicted from the cache
    """
    if value is not None:
        value.close()
