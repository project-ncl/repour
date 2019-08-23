import asyncio
import logging
import os

CALLBACK_LOGS_PATH = os.environ.get("LOGS_FOLDER", '/tmp/repour-logs-callback')


def get_callback_log_path(callback_id):
    return os.path.join(CALLBACK_LOGS_PATH, callback_id + '.log')


class FileCallbackHandler(logging.StreamHandler):
    """
    Handler that logs into {directory}/{callback_id}.log
    """
    def __init__(self, directory=CALLBACK_LOGS_PATH, mode='a', encoding=None, delay=None):
        if os.path.exists(directory):
            if not os.path.isdir(directory):
                raise Exception(directory + " is not a directory! Can't log there")
        else:
            os.makedirs(directory)

        self.filename = directory
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        logging.Handler.__init__(self)

    def emit(self, record):
        try:
            task = asyncio.Task.current_task()

            if task is not None:
                callback_id = getattr(task, "callback_id", None)
                if callback_id is not None:
                    self.stream = self._open_callback_file(callback_id)
                    logging.StreamHandler.emit(self, record)
        except:
            self.handleError(record)

    def _open_callback_file(self, callback_id):
        path = get_callback_log_path(callback_id)
        return open(path, self.mode, encoding=self.encoding)