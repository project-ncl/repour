# flake8: noqa
import json
import unittest

from repour import exception
import repour.adjust.project_manipulator_provider as project_manipulator_provider


class TestProjectManipulatorProvider(unittest.TestCase):
    def test_get_extra_parameters(self):
        param = {"ALIGNMENT_PARAMETERS": None}
        self.assertEqual(project_manipulator_provider.get_extra_parameters(param), [])

        param = {"ALIGNMENT_PARAMETERS": "-Dhello-world --letsgo"}
        self.assertEqual(
            project_manipulator_provider.get_extra_parameters(param),
            ["-Dhello-world", "--letsgo"],
        )

        try:
            param = {"ALIGNMENT_PARAMETERS": '-DdependencyOverride.*:*@*="'}
            project_manipulator_provider.get_extra_parameters(param)
            self.assertFalse(True, msg="An exception should be thrown here")
        except exception.AdjustCommandError as e:
            self.assertEqual(e.exit_code, 10)

        try:
            param = {"ALIGNMENT_PARAMETERS": "test 1234"}
            project_manipulator_provider.get_extra_parameters(param)
            self.assertFalse(True, msg="An exception should be thrown here")
        except exception.AdjustCommandError as e:
            self.assertEqual(e.exit_code, 10)
