import subprocess
import tempfile

import repour.repo

class TemporaryGitDirectory(tempfile.TemporaryDirectory):
    def __init__(self, bare=False, origin=None, ro_url=None):
        super().__init__()
        self.bare = bare
        self.origin = origin
        self.ro_url = ro_url

    def __enter__(self):
        cmd = ["git", "init"]
        if self.bare:
            cmd.append("--bare")
        cmd.append(self.name)
        quiet_check_call(cmd)

        if self.origin is not None:
            quiet_check_call(["git", "-C", self.name, "remote", "add", "origin", self.origin])

        if self.ro_url is not None:
            return repour.repo.RepoUrls(readonly=self.ro_url, readwrite=self.name)
        else:
            return self.name

def quiet_check_call(cmd):
    return subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
