import asyncio
import tempfile
import unittest

import repour.adjust.gradle_provider as gradle_provider


class TestGradleProvider(unittest.TestCase):
    def test_gradle_command(self):

        f = tempfile.TemporaryDirectory()

        temp_gradle_file = open(f.name + "/gradlew", "w")
        temp_gradle_file.write("test123")
        temp_gradle_file.close()

        self.assertEqual("./gradlew", gradle_provider.get_command_gradle(f.name))
        f.cleanup()

        no_gradlew_folder = tempfile.TemporaryDirectory()

        self.assertEqual(
            "gradle", gradle_provider.get_command_gradle(no_gradlew_folder.name)
        )

        no_gradlew_folder.cleanup()
