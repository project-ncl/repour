# flake8: noqa
import asyncio
import unittest

from repour.config import config
import repour.server.endpoint.external_to_internal as external_to_internal

loop = asyncio.get_event_loop()


class TestExternalToInternal(unittest.TestCase):
    def test_translate_external_to_internal(self):
        c = loop.run_until_complete(config.get_configuration())
        gerrit_server = c.get("git_url_internal_template", None)

        valid_external_urls = [
            "http://github.com/myproject/myrepo.git",
            "https://github.com/myproject/myrepo/",
            "git+ssh://github.com/myproject/myrepo.git",
            "git@github.com:myproject/myrepo.git",
            "git@github.com/myproject/myrepo.git",
            "ssh://git@github.com/myproject/myrepo.git",
        ]

        invalid_external_urls = [
            "://github.com/myproject/myrepo.git",
            "github.com/myproject/myrepo.git",
            "sh://github.com/myproject/myrepo.git",
        ]

        internal_url = f"{gerrit_server}/myproject/myrepo.git"

        for external in valid_external_urls:
            result = loop.run_until_complete(
                external_to_internal.translate_external_to_internal(external)
            )
            self.assertEqual(result, internal_url)

        for external in invalid_external_urls:
            with self.assertRaises(Exception):
                loop.run_until_complete(
                    external_to_internal.translate_external_to_internal(external)
                )
