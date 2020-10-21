# flake8: noqa
import unittest
import repour.server.endpoint.internal_scm as internal_scm


class TestInternalSCM(unittest.TestCase):

    def test_build_gerrit_command(self):
        result = internal_scm.build_gerrit_command(
            "project1",
            "parent-project",
            ["owner1", "owner2"],
            "description1 description2",
        )

        # test if description specified
        self.assertTrue("-d 'description1 description2'" in result)

        # Test if owner parameters are specified
        self.assertTrue("-o 'owner1'" in result)
        self.assertTrue("-o 'owner2'" in result)

        # Test if parent project specified
        self.assertTrue("-p 'parent-project'" in result)

        # Test if command invoked properly
        self.assertTrue("gerrit create-project 'project1.git'" in result)
