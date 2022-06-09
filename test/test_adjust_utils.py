# flake8: noqa
import unittest

import repour.adjust.util as util


class TestAdjustUtil(unittest.TestCase):
    def test_util_file_option(self):

        param = {"ALIGNMENT_PARAMETERS": "-Dtest=test -f haha/pom.xml"}

        remaining_args, filepath = util.get_extra_parameters(param)

        self.assertEqual(remaining_args, ["-Dtest=test"])
        self.assertEqual(filepath, "haha/pom.xml")

        param_file = {"ALIGNMENT_PARAMETERS": "--file hoho/test.xml -Dtest=test"}

        remaining_args, filepath = util.get_extra_parameters(param_file)
        self.assertEqual(remaining_args, ["-Dtest=test"])
        self.assertEqual(filepath, "hoho/test.xml")

        param_file_equal = {
            "ALIGNMENT_PARAMETERS": "-Dtest2=test2 --file=hihi -Dtest=test"
        }

        remaining_args, filepath = util.get_extra_parameters(param_file_equal)
        self.assertEqual(remaining_args, ["-Dtest2=test2", "-Dtest=test"])
        self.assertEqual(filepath, "hihi")
