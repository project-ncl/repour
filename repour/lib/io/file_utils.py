import os


def read_last_bytes_of_file(file_path: str, size_in_bytes: int) -> str:
    """
    Return the last bytes of a file containing utf-8 formatted text rather than the whole contents. The last bytes is
    determined by size_in_bytes

    Parameters:
    - file_path: file path to read
    - size_in_bytes: amount of data to read in bytes

    Returns:
    - :str: of file content in utf-8 format
    """
    with open(file_path, "rb") as file:
        # Note the minus sign
        file.seek(-size_in_bytes, os.SEEK_END)
        content = file.read().decode("utf-8")
        return content
