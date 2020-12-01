# flake8: noqa
import unittest
import tempfile

import repour.adjust.util as util

import repour.exception as exception


class TestUtil(unittest.TestCase):
    def test_get_jvm_from_extra_parameters(self):

        extra_params = ["-DRepour_Java=1.8.0", "not appropriate"]
        jvm = util.get_jvm_from_extra_parameters(extra_params)

        self.assertEqual("1.8.0", jvm)

        extra_params = ["not really", "not appropriate"]

        jvm_not_specified = util.get_jvm_from_extra_parameters(extra_params)
        self.assertEqual(None, jvm_not_specified)

    def test_verify_folder_exists(self):

        # create temp folder
        with tempfile.TemporaryDirectory() as tmpdirname:

            # no exception should be thrown
            util.verify_folder_exists(str(tmpdirname), "error")

        with tempfile.NamedTemporaryFile() as f:
            self.assertRaises(
                exception.CommandError, util.verify_folder_exists, f.name, "error"
            )

        with tempfile.NamedTemporaryFile() as f:
            self.assertRaises(
                exception.CommandError,
                util.verify_folder_exists,
                f.name + "donotexist",
                "error",
            )
