import asyncio
import os
import shutil
import subprocess
import tempfile
import unittest

import repour.asgit
import repour.adjust
from test import util

loop = asyncio.get_event_loop()

class TestAdjust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Dummy git origin
        cls.origin_git_cls = util.TemporaryGitDirectory(ro_url="fake-ro-url")
        cls.origin_git = cls.origin_git_cls.__enter__()

        with open(os.path.join(cls.origin_git.readwrite, "asd.txt"), "w") as f:
            f.write("Hello")

        util.quiet_check_call(["git", "-C", cls.origin_git.readwrite, "add", "-A"])
        util.quiet_check_call(["git", "-C", cls.origin_git.readwrite, "commit", "-m", "Pull"])

        # Convert to bare
        os.remove(os.path.join(cls.origin_git.readwrite, "asd.txt"))
        git_dir = os.path.join(cls.origin_git.readwrite, ".git")
        for fn in os.listdir(git_dir):
            shutil.move(os.path.join(git_dir, fn), cls.origin_git.readwrite)
        os.rmdir(git_dir)
        util.quiet_check_call(["git", "-C", cls.origin_git.readwrite, "config", "--bool", "core.bare", "true"])

    @classmethod
    def tearDownClass(cls):
        cls.origin_git_cls.cleanup()

    def test_standalone(self):
        @asyncio.coroutine
        def adjust(d):
            with open(os.path.join(d, "asd.txt"), "w") as f:
                f.write("Hello Hello")
            return "test"

        @asyncio.coroutine
        def repo_provider(p, create):
            return self.origin_git

        d = loop.run_until_complete(repour.adjust.adjust(
            adjustspec={
                "name": "test",
                "ref": "master",
            },
            repo_provider=repo_provider,
            adjust_provider=adjust,
        ))
        self.assertRegex(d["branch"], r'^adjust-[0-9]+$')
        self.assertRegex(d["tag"], r'^adjust-[0-9]+-root$')
