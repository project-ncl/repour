import unittest

import voluptuous

import repour.validation

class TestPrimitives(unittest.TestCase):
    def test_nonempty_str(self):
        self.assertEqual("asd", repour.validation.nonempty_str("asd"))
        self.assertEqual("asd qwe", repour.validation.nonempty_str("asd qwe"))
        self.assertEqual(" ", repour.validation.nonempty_str(" "))

        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_str("")
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_str(0)
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_str(False)

    def test_nonempty_noblank_str(self):
        self.assertEqual("asd", repour.validation.nonempty_noblank_str("asd"))

        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_noblank_str("")
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_noblank_str("\n")
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_noblank_str("asd qwe")
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_noblank_str(1)
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.nonempty_noblank_str(True)

    def test_port_num(self):
        self.assertEqual(65535, repour.validation.port_num(65535))

        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.port_num(0)
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.port_num(65536)
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.port_num("1000")
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.port_num(False)

    def test_name_str(self):
        self.assertEqual("asd", repour.validation.name_str("asd"))
        self.assertEqual("ASD", repour.validation.name_str("ASD"))
        self.assertEqual("123", repour.validation.name_str("123"))
        self.assertEqual("_", repour.validation.name_str("_"))
        self.assertEqual("asd-1.5.0", repour.validation.name_str("asd-1.5.0"))
        self.assertEqual("_ASD-", repour.validation.name_str("_ASD-"))

        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str("")
        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str(" ")
        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str("-asd-1.5.0")
        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str("asd!1.5.0")
        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str("%")
        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str(0)
        with self.assertRaises(voluptuous.MatchInvalid):
            repour.validation.name_str(False)

class TestAdjust(unittest.TestCase):
    def test_adjust(self):
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
        }
        self.assertEqual(valid, repour.validation.adjust(valid))

        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({})
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({
                "name": "someproject",
            })
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({
                "ref": "2.2.11.Final",
            })
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({
                "name": "someproject",
                "ref": "",
            })
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({
                "name": "",
                "ref": "2.2.11.Final",
            })
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({
                "name": "someproject",
                "ref": "2.2.11.Final",
                "asd": "123",
            })

    def test_callback(self):
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
            "callback": {
                "url": "http://localhost/asd"
            },
        }
        self.assertEqual(valid, repour.validation.adjust(valid))
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
            "callback": {
                "url": "http://localhost/asd",
                "method": "POST",
            },
        }
        self.assertEqual(valid, repour.validation.adjust(valid))
        valid = {
            "name": "someproject",
            "ref": "2.2.11.Final",
            "callback": {
                "url": "http://localhost/asd",
                "method": "PUT",
            },
        }
        self.assertEqual(valid, repour.validation.adjust(valid))
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.adjust({
                "name": "someproject",
                "ref": "2.2.11.Final",
                "callback": {
                    "url": "http://localhost/asd",
                    "method": "GET",
                },
            })

class TestPull(unittest.TestCase):
    def test_pull(self):
        def check_adjust(d):
            d["adjust"] = True
            self.assertEqual(d, repour.validation.pull(d))
            d["adjust"] = False
            self.assertEqual(d, repour.validation.pull(d))

        valid_scm = {
            "name": "someproject",
            "type": "git",
            "ref": "2.2.11.Final",
            "url": "git://example.com/someproject.git",
        }
        self.assertEqual(valid_scm, repour.validation.pull(valid_scm))
        check_adjust(valid_scm)

        valid_scm["type"] = "hg"
        self.assertEqual(valid_scm, repour.validation.pull(valid_scm))
        check_adjust(valid_scm)

        del valid_scm["ref"]
        self.assertEqual(valid_scm, repour.validation.pull(valid_scm))
        check_adjust(valid_scm)

        valid_archive = {
            "name": "someproject",
            "type": "archive",
            "url": "http://example.com/someproject.tar.gz",
        }
        self.assertEqual(valid_archive, repour.validation.pull(valid_archive))
        check_adjust(valid_archive)

        with self.assertRaises(voluptuous.MultipleInvalid):
            valid_archive["name"] = ""
            repour.validation.pull(valid_archive)
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.pull({})
        with self.assertRaises(voluptuous.MultipleInvalid):
            repour.validation.pull({
                "name": "someproject",
            })
        with self.assertRaises(voluptuous.MultipleInvalid):
            invalid = valid_scm.copy()
            invalid["asd"] = "asd"
            repour.validation.pull(invalid)
        with self.assertRaises(voluptuous.MultipleInvalid):
            invalid = valid_scm.copy()
            invalid["url"] = 123
            repour.validation.pull(invalid)

    def test_callback(self):
        valid = {
            "name": "someproject",
            "type": "archive",
            "url": "http://example.com/someproject.tar.gz",
            "callback": {
                "url": "http://localhost/asd",
            },
        }
        self.assertEqual(valid, repour.validation.pull(valid))

class TestServerConfig(unittest.TestCase):
    def test_server_config(self):
        valid = {
            "log": {
                "level": "ERROR",
                "path": "/home/repour/server.log",
            },
            "bind": {
                "address": None,
                "port": 80,
            },
            "adjust_provider": {
                "type": "subprocess",
                "params": {
                    "cmd": ["/bin/true"],
                },
            },
            "repo_provider": {
                "type": "gitlab",
                "params": {
                    "api_url": "http://gitlab.example.com",
                    "username": "repour",
                    "password": "cxz321",
                },
            },
        }
        self.assertEqual(valid, repour.validation.server_config(valid))
