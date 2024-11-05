# flake8: noqa
import unittest
import repour.server.endpoint.internal_scm_gitlab as internal_scm_gitlab


class TestInternalSCMGitlab(unittest.TestCase):
    def test_internal_scm_gitlab(self):
        result = internal_scm_gitlab.sanitize_gitlab_project_path("Qix-/color-convert")
        self.assertEqual(result, "Qix_/color-convert")

        result = internal_scm_gitlab.sanitize_gitlab_project_path("-Qix/color-convert")
        self.assertEqual(result, "_Qix/color-convert")

        result = internal_scm_gitlab.sanitize_gitlab_project_path("Qix/color-convert-")
        self.assertEqual(result, "Qix/color-convert_")
