# flake8: noqa
import unittest

import repour.server.endpoint.validation as validation
import voluptuous


class TestPrimitives(unittest.TestCase):
    def test_nonempty_str(self):
        self.assertEqual("asd", validation.nonempty_str("asd"))
        self.assertEqual("asd qwe", validation.nonempty_str("asd qwe"))
        self.assertEqual(" ", validation.nonempty_str(" "))

        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_str("")
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_str(0)
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_str(False)

    def test_nonempty_noblank_str(self):
        self.assertEqual("asd", validation.nonempty_noblank_str("asd"))

        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_noblank_str("")
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_noblank_str("\n")
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_noblank_str("asd qwe")
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_noblank_str(1)
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.nonempty_noblank_str(True)

    def test_port_num(self):
        self.assertEqual(65535, validation.port_num(65535))

        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.port_num(0)
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.port_num(65536)
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.port_num("1000")
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.port_num(False)

    def test_name_str(self):
        self.assertEqual("asd", validation.name_str("asd"))
        self.assertEqual("ASD", validation.name_str("ASD"))
        self.assertEqual("123", validation.name_str("123"))
        self.assertEqual("_", validation.name_str("_"))
        self.assertEqual("asd-1.5.0", validation.name_str("asd-1.5.0"))
        self.assertEqual("_ASD-", validation.name_str("_ASD-"))

        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str("")
        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str(" ")
        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str("-asd-1.5.0")
        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str("asd!1.5.0")
        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str("%")
        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str(0)
        with self.assertRaises(voluptuous.MatchInvalid):
            validation.name_str(False)


class TestAdjust(unittest.TestCase):
    def test_adjust(self):
        valid = {"name": "someproject", "ref": "2.2.11.Final"}
        self.assertEqual(valid, validation.adjust(valid))

        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust({})
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust({"name": "someproject"})
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust({"ref": "2.2.11.Final"})
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust({"name": "someproject", "ref": ""})
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust({"name": "", "ref": "2.2.11.Final"})
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust(
                {"name": "someproject", "ref": "2.2.11.Final", "asd": "123"}
            )

    def test_callback(self):
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
            "callback": {"url": "http://localhost/asd"},
        }
        self.assertEqual(valid, validation.adjust(valid))
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
            "callback": {"url": "http://localhost/asd", "method": "POST"},
        }
        self.assertEqual(valid, validation.adjust(valid))
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
            "callback": {"url": "http://localhost/asd", "method": "PUT"},
        }
        self.assertEqual(valid, validation.adjust(valid))
        with self.assertRaises(voluptuous.MultipleInvalid):
            validation.adjust(
                {
                    "name": "someproject",
                    "ref": "2.2.11.Final",
                    "callback": {"url": "http://localhost/asd", "method": "GET"},
                }
            )


class TestServerConfig(unittest.TestCase):
    def test_server_config(self):
        valid = {
            "log": {"level": "ERROR", "path": "/home/repour/server.log"},
            "bind": {"address": None, "port": 80},
            "adjust_provider": {"type": "subprocess", "params": {"cmd": ["/bin/true"]}},
            "repo_provider": {
                "type": "gitlab",
                "params": {
                    "api_url": "http://gitlab.example.com",
                    "username": "repour",
                    "password": "cxz321",
                },
            },
        }
        self.assertEqual(valid, validation.server_config(valid))


class TestClone(unittest.TestCase):
    def test_clone_validation(self):
        valid = {
            "type": "git",
            "ref": None,
            "originRepoUrl": "http://github.com/project-ncl/repour.git",
            "targetRepoUrl": "git+ssh://gerrit.com/project-ncl/repour.git",
        }
        self.assertEqual(valid, validation.clone(valid))

    def test_clone_validation_with_git_scp_url(self):
        valid = {
            "type": "git",
            "ref": None,
            "originRepoUrl": "git@github.com:project-ncl/repour.git",
            "targetRepoUrl": "git+ssh://gerrit.com/project-ncl/repour.git",
        }
        self.assertEqual(valid, validation.clone(valid))
