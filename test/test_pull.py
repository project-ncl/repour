import asyncio
import datetime
import io
import os
import shutil
import subprocess
import tarfile
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
                    origin_ref="v1.0",
                ))

                self.assertRegex(d["tag"], r'^repour-[0-9a-f]+$')

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
                    origin_ref="v1.0",
                ))

                self.assertRegex(d["tag"], r'^repour-[0-9a-f]+$')
                self.assertRegex(d["pull"]["tag"], r'^repour-[0-9a-f]+$')

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
                    origin_ref="v1.0",
                ))

                self.assertRegex(d["tag"], r'^repour-[0-9a-f]+$')

class TestPull(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Dummy git origin
        cls.origin_git_cls = util.TemporaryGitDirectory()
        cls.origin_git = cls.origin_git_cls.__enter__()

        with open(os.path.join(cls.origin_git, "asd.txt"), "w") as f:
            f.write("Origin")

        util.quiet_check_call(["git", "-C", cls.origin_git, "add", "-A"])
        util.quiet_check_call(["git", "-C", cls.origin_git, "commit", "-m", "Some origin commit"])

        cls.origin_git = "file://" + cls.origin_git

        # Dummy archive origin
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:xz") as t:
            i = tarfile.TarInfo("asd.txt")

            b = io.BytesIO(b"Hello\n")
            b.seek(0, io.SEEK_END)
            i.size = b.tell()
            b.seek(0)

            t.addfile(i, b)

        # Dummy archive origin (with single root dir)
        srd_tar_buf = io.BytesIO()
        with tarfile.open(fileobj=srd_tar_buf, mode="w:xz") as t:
            i = tarfile.TarInfo("srd/asd.txt")

            b = io.BytesIO(b"Hello\n")
            b.seek(0, io.SEEK_END)
            i.size = b.tell()
            b.seek(0)

            t.addfile(i, b)

        util.setup_http(
            cls=cls,
            loop=loop,
            routes=[
                ("GET", "/test.tar.xz", util.http_write_handler(tar_buf)),
                ("GET", "/srd_test.tar.xz", util.http_write_handler(srd_tar_buf)),
            ],
        )

    @classmethod
    def tearDownClass(cls):
        cls.origin_git_cls.cleanup()
        util.teardown_http(cls, loop)

    def test_git(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with tempfile.TemporaryDirectory() as repo:
                @asyncio.coroutine
                def adjust(d):
                    return "test"

                @asyncio.coroutine
                def repo_provider(p):
                    return remote

                d_shallow = loop.run_until_complete(repour.pull.pull(
                    pullspec={
                        "name": "test",
                        "type": "git",
                        "ref": "master",
                        "url": self.origin_git,
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                ))
                self.assertIsInstance(d_shallow, dict)

                d_deep = loop.run_until_complete(repour.pull.pull(
                    pullspec={
                        "name": "test",
                        "type": "git",
                        # Use HEAD here, normally would expect this to be a
                        # commit id, but does the same thing of triggering deep
                        # clone.
                        "ref": "HEAD",
                        "url": self.origin_git,
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                ))
                # Deduplication should be activated
                self.assertEqual(d_deep, d_shallow)

    @unittest.skipIf(shutil.which("hg") is None, "requires mercurial")
    def test_hg(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with util.TemporaryHgDirectory(add_commit=True) as origin_hg:
                @asyncio.coroutine
                def adjust(d):
                    return "test"

                @asyncio.coroutine
                def repo_provider(p):
                    return remote

                d = loop.run_until_complete(repour.pull.pull(
                    pullspec={
                        "name": "test",
                        "type": "hg",
                        "ref": "tip",
                        "url": origin_hg,
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                ))
                self.assertIsInstance(d, dict)

    def test_archive(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with tempfile.TemporaryDirectory() as repo:
                @asyncio.coroutine
                def adjust(d):
                    return "test"

                @asyncio.coroutine
                def repo_provider(p):
                    return remote

                d = loop.run_until_complete(repour.pull.pull(
                    pullspec={
                        "name": "test",
                        "type": "archive",
                        "url": self.url + "/test.tar.xz",
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                ))
                self.assertIsInstance(d, dict)

                new_d = loop.run_until_complete(repour.pull.pull(
                    pullspec={
                        "name": "test",
                        "type": "archive",
                        "url": self.url + "/srd_test.tar.xz",
                    },
                    repo_provider=repo_provider,
                    adjust_provider=adjust,
                ))
                # Single root directory should be shucked, resulting in deduplication
                self.assertEqual(d, new_d)
