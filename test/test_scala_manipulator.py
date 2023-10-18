# flake8: noqa
import json
import unittest

from repour import exception
import repour.adjust.scala_provider as scala_provider


class TestScalaProvider(unittest.TestCase):
    def test_get_extra_parameters(self):
        param = {"ALIGNMENT_PARAMETERS": None}
        self.assertEqual(scala_provider.get_extra_parameters(param), [])

        param = {"ALIGNMENT_PARAMETERS": "-Dhello-world --letsgo"}
        self.assertEqual(
            scala_provider.get_extra_parameters(param), ["-Dhello-world", "--letsgo"]
        )

        try:
            param = {"ALIGNMENT_PARAMETERS": '-DdependencyOverride.*:*@*="'}
            scala_provider.get_extra_parameters(param)
            self.assertFalse(True, msg="An exception should be thrown here")
        except exception.AdjustCommandError as e:
            self.assertEqual(e.exit_code, 10)

        try:
            param = {"ALIGNMENT_PARAMETERS": "test 1234"}
            scala_provider.get_extra_parameters(param)
            self.assertFalse(True, msg="An exception should be thrown here")
        except exception.AdjustCommandError as e:
            self.assertEqual(e.exit_code, 10)
