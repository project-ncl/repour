import asyncio
import datetime
import os
import subprocess
import tempfile
import unittest

import repour.pull
from test import util

loop = asyncio.get_event_loop()

class TestToInternal(unittest.TestCase):
    def test_to_internal(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with tempfile.TemporaryDirectory() as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")
                d = loop.run_until_complete(repour.pull.to_internal(
                    internal_repo_url=remote,
                    dirname=repo,
                    origin_ref="v1.0",
                    origin_url="git://example.com/repo",
                    origin_type="git",
                ))
                self.assertIsInstance(d, dict)
            out = subprocess.check_output(["git", "-C", remote.readwrite, "tag", "-l", "-n5"])
            self.assertIn(b"""Origin: git://example.com/repo
    Reference: v1.0
    Type: git""", out)

class TestProcessSourceTree(unittest.TestCase):
    def test_no_adjust(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with tempfile.TemporaryDirectory() as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")

                @asyncio.coroutine
                def repo_provider(p):
                    return remote

                d = loop.run_until_complete(repour.pull.process_source_tree(
                    pullspec={
                        "name": "test",
                        "type": "git",
                        "ref": "v1.0",
                        "url": "git://example.com",
                        "adjust": False,
                    },
                    repo_provider=repo_provider,
                    adjust_provider=None,
                    repo_dir=repo,
                    origin_type="git",
                ))

                self.assertRegex(d["branch"], r'^pull-[0-9]+$')
                self.assertRegex(d["tag"], r'^pull-[0-9]+-root$')

    def test_with_adjust(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with tempfile.TemporaryDirectory() as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")

                @asyncio.coroutine
                def adjust(d):
                    with open(os.path.join(repo, "asd.txt"), "w") as f:
                        f.write("Hello Hello")
                    return "test"

                @asyncio.coroutine
                def repo_provider(p):
                    return remote

                d = loop.run_until_complete(repour.pull.process_source_tree(
                    pullspec={
                        "name": "test",
                        "type": "git",
                        "ref": "v1.0",
                        "url": "git://example.com",
                        "adjust": True,
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                    repo_dir=repo,
                    origin_type="git",
                ))

                self.assertRegex(d["branch"], r'^adjust-[0-9]+$')
                self.assertRegex(d["tag"], r'^adjust-[0-9]+-root$')
                self.assertRegex(d["pull"]["branch"], r'^pull-[0-9]+$')
                self.assertRegex(d["pull"]["tag"], r'^pull-[0-9]+-root$')

                # Verify adjust commit is child of pull commit
                out = subprocess.check_output(["git", "-C", remote.readwrite, "rev-list", "--parents", "-n1", d["tag"]])
                adjust_commit, adjust_parent = out.decode("utf-8").strip().split(" ")
                out = subprocess.check_output(["git", "-C", remote.readwrite, "rev-list", "-n1", d["pull"]["tag"]])
                pull_commit = out.decode("utf-8").strip()

                self.assertEqual(adjust_parent, pull_commit)
                self.assertNotEqual(adjust_commit, pull_commit)

    def test_with_adjust_noop(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with tempfile.TemporaryDirectory() as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")

                @asyncio.coroutine
                def adjust(d):
                    return "test"

                @asyncio.coroutine
                def repo_provider(p):
                    return remote

                d = loop.run_until_complete(repour.pull.process_source_tree(
                    pullspec={
                        "name": "test",
                        "type": "git",
                        "ref": "v1.0",
                        "url": "git://example.com",
                        "adjust": True,
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                    repo_dir=repo,
                    origin_type="git",
                ))

                self.assertRegex(d["branch"], r'^pull-[0-9]+$')
                self.assertRegex(d["tag"], r'^pull-[0-9]+-root$')

class TestPull(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin_cls = util.TemporaryGitDirectory()
        cls.origin = cls.origin_cls.__enter__()

        with open(os.path.join(cls.origin, "asd.txt"), "w") as f:
            f.write("Origin")

        util.quiet_check_call(["git", "-C", cls.origin, "add", "-A"])
        util.quiet_check_call(["git", "-C", cls.origin, "commit", "-m", "Some origin commit"])

    @classmethod
    def tearDownClass(cls):
        cls.origin_cls.cleanup()

    def test_(self):
        pass

class Test(unittest.TestCase):
    def test_(self):
        pass
