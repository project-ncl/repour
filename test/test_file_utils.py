import tempfile
import unittest

from repour.lib.io import file_utils


class TestFileUtils(unittest.TestCase):
    def test_read_last_bytes_of_file(self):
        fp = tempfile.NamedTemporaryFile()
        fp.write(b"1234567890")
        fp.flush()

        data = file_utils.read_last_bytes_of_file(fp.name, 5)
        self.assertEqual("67890", data)

        fp.close()
