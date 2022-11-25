import asyncio
import logging


def add_update_mdc_key_value_in_task(key, value):
    """
    Add an mdc key/value to the task mdc attribute. This is used to also set the log context
    """
    task = asyncio.current_task()

    if getattr(task, "mdc", None) is None:
        task.mdc = {}

    task.mdc[key] = value


def remove_mdc_key_in_task(key):
    """
    Delete a key from the task mdc attribute if present
    """

    task = asyncio.current_task()

    if getattr(task, "mdc", None) is not None:
        if key in task.mdc:
            del task.mdc[key]

def get_mdc_value_in_task(key):
    """
    Given a key, returns the mdc value from the task.
    """
    task = asyncio.current_task()

    if getattr(task, "mdc", None) is not None:
        if key in task.mdc:
            return task.mdc[key]
    return None

class CustomFormatter(logging.Formatter):
    """
    Logging Formatter apply default formatting, unless the logger name is custom_logger_name
    """

    def __init__(self, default_logger_style, custom_logger_name, custom_logger_style):
        self.default_logger_style = default_logger_style
        self.custom_logger_name = custom_logger_name
        self.custom_logger_style = custom_logger_style

    def format(self, record):
        if record.name == self.custom_logger_name:
            formatter = logging.Formatter(self.custom_logger_style, style="{")
        else:
            formatter = logging.Formatter(self.default_logger_style, style="{")

        return formatter.format(record)
