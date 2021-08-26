# flake8: noqa
import json
import unittest

from repour import exception
import repour.adjust.pme_provider as pme_provider


class TestPMEProvider(unittest.TestCase):
    def test_parse_pme_result_manipulation_format(self):

        group_id = "org.apache.activemq"
        artifact_id = "artemis-pom"
        version = "2.6.3.redhat-00021"

        raw_result_data = {
            "executionRoot": {
                "groupId": group_id,
                "artifactId": artifact_id,
                "version": version,
            }
        }

        result = pme_provider.parse_pme_result_manipulation_format(
            "/tmp", "", json.dumps(raw_result_data), None, None
        )
        self.verify_result_format(result, group_id, artifact_id, version, [])

        result = pme_provider.parse_pme_result_manipulation_format(
            "/tmp", "", json.dumps(raw_result_data), "group", "artifact"
        )
        self.verify_result_format(result, "group", "artifact", version, [])

    def test_pme_disabled(self):

        param = {"ALIGNMENT_PARAMETERS": None}
        self.assertFalse(pme_provider.is_pme_disabled_via_extra_parameters(param))

        param = {"ALIGNMENT_PARAMETERS": "-Dmanipulation.disable=true --letsgo"}
        self.assertTrue(pme_provider.is_pme_disabled_via_extra_parameters(param))

        param = {"ALIGNMENT_PARAMETERS": "-Dmanipulation.disable=false --letsgo"}
        self.assertFalse(pme_provider.is_pme_disabled_via_extra_parameters(param))

        param = {"ALIGNMENT_PARAMETERS": '-DdependencyOverride.*:*@*="'}

        try:
            pme_provider.is_pme_disabled_via_extra_parameters(param)
            self.assertFalse(True, msg="An exception should be thrown here")
        except exception.AdjustCommandError as e:
            self.assertEqual(e.exit_code, 10)

    def verify_result_format(
        self, result, group_id, artifact_id, version, removed_repositories
    ):

        result_simplified = result["VersioningState"]["executionRootModified"]

        self.assertEqual(result_simplified["groupId"], group_id)
        self.assertEqual(result_simplified["artifactId"], artifact_id)

        if version is not None:
            self.assertEqual(result_simplified["version"], version)

        self.assertEqual(result["RemovedRepositories"], removed_repositories)
