import asyncio

def add_update_mdc_key_value_in_task(key, value):
    """
    Add an mdc key/value to the task mdc attribute. This is used to also set the log context
    """
    task = asyncio.Task.current_task()

    if getattr(task, "mdc", None) is None:
        task.mdc = {}

    task.mdc[key] = value


def remove_mdc_key_in_task(key):
    """
    Delete a key from the task mdc attribute if present
    """

    task = asyncio.Task.current_task()

    if getattr(task, "mdc", None) is not None:
        if key in task.mdc:
            del task.mdc[key]