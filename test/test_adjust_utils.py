import asyncio
import unittest
import repour.adjust.util as util

loop = asyncio.get_event_loop()

class TestAdjustUtil(unittest.TestCase):

    def test_util_file_option(self):

        param = {"CUSTOM_PME_PARAMETERS": "-Dtest=test -f haha/pom.xml"}

        remaining_args, filepath = loop.run_until_complete(util.get_extra_parameters(param))

        self.assertEqual(remaining_args, ['-Dtest=test'])
        self.assertEqual(filepath, "haha/")

        param_file = {"CUSTOM_PME_PARAMETERS": "--file hoho/pom.xml -Dtest=test"}

        remaining_args, filepath = loop.run_until_complete(util.get_extra_parameters(param_file))
        self.assertEqual(remaining_args, ['-Dtest=test'])
        self.assertEqual(filepath, "hoho/")

        param_file_equal = {"CUSTOM_PME_PARAMETERS": "-Dtest2=test2 --file=hihi -Dtest=test"}

        remaining_args, filepath = loop.run_until_complete(util.get_extra_parameters(param_file_equal))
        self.assertEqual(remaining_args, ['-Dtest2=test2', '-Dtest=test'])
        self.assertEqual(filepath, "hihi")