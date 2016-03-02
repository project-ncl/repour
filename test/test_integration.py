import http.server
import io
import json
import os
import pprint
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
import warnings

import yaml

try:
    import docker
    import requests
    deps_available=True
except ImportError:
    deps_available=False

import repour.validation

# Only run integration tests if able and requested
run_integration_tests = deps_available and "REPOUR_RUN_IT" in os.environ

#
# Utils
#

def wait_in_logs(client, container, target_text):
    log = client.logs(
        container=container,
        stream=True,

    )

    for raw_line in log:
        line = raw_line.decode("utf-8")
        if target_text in line:
            break
    else:
        raise Exception("Container exited before target text '{target_text}' was found".format(**locals()))

#
# Tests
#

if run_integration_tests:
    da_url = "http://10.19.208.25:8180/da/rest/v-0.4/reports/lookup/gavs"

    class TestGitoliteIntegration(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            # current file is in test/ relative to repo root
            repo_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

            # Docker client
            cls.client = docker.Client(version="1.19")

            # Build images
            def build_image(dockerfile, tag):
                for logline in cls.client.build(
                    path=repo_root,
                    dockerfile=dockerfile,
                    rm=True,
                    forcerm=True,
                    tag=tag,
                ):
                    pass
                assert b"Successfully built" in logline, "Build of image {tag} failed".format(**locals())

            repour_it_image = "repour_integration_test"
            build_image("Dockerfile", repour_it_image)
            repour_it_git_image = "repour_integration_test_git"
            build_image("Dockerfile.gitolite", repour_it_git_image)

            # Create OSE-like Secrets volume dir
            cls.config_dir = tempfile.TemporaryDirectory()

            # Create key pairs
            for n in ["repour", "admin"]:
                key_dir = os.path.join(cls.config_dir.name, n)
                os.mkdir(key_dir)
                priv_key = os.path.join(key_dir, n)
                subprocess.check_call(["ssh-keygen", "-q", "-f", priv_key, "-N", ""])
            key_owner = os.getuid()

            cls.containers = []
            try:
                # Create/start Git
                git_container = cls.client.create_container(
                    image=repour_it_git_image,
                    detach=True,
                    host_config=cls.client.create_host_config(
                        binds={
                            cls.config_dir.name: {
                                "bind": "/mnt/secrets",
                                "mode": "z",
                            }
                        },
                    ),
                    user=key_owner,
                )["Id"]
                cls.containers.append(git_container)
                cls.client.start(git_container)
                cls.git_container = git_container
                wait_in_logs(cls.client, git_container, "==> Ready")
                git_hostname = cls.client.inspect_container(git_container)["NetworkSettings"]["IPAddress"]

                # Create/start Repour
                repour_container = cls.client.create_container(
                    image=repour_it_image,
                    detach=True,
                    host_config=cls.client.create_host_config(
                        links={ git_container: "git" },
                        binds={
                            cls.config_dir.name: {
                                "bind": "/mnt/secrets",
                                "mode": "z",
                            }
                        },
                    ),
                    # Note that the forced UID change activates au.py, so
                    # setting REPOUR_GITOLITE_SSH_USER isn't required (will be
                    # source default user git instead of gitolite3)
                    user=key_owner,
                    environment={
                        "REPOUR_GITOLITE_HOST": git_hostname,
                        "REPOUR_PME_DA_URL": da_url,
                    }
                )["Id"]
                cls.containers.append(repour_container)
                cls.client.start(repour_container)
                cls.repour_container = repour_container
                wait_in_logs(cls.client, repour_container, "Server started on socket")
                repour_hostname = cls.client.inspect_container(repour_container)["NetworkSettings"]["IPAddress"]
                cls.repour_api_url="http://{repour_hostname}:7331".format(**locals())

                cls.requests_session = requests.Session()

                # For run(s) to activate the log dumper in tearDownClass
                cls.dump_logs = set()
            except Exception:
                print("\n\nContainer Startup Logs:")
                for container in cls.containers:
                    print(cls.client.logs(container).decode("utf-8"))
                    print()
                    cls.client.remove_container(
                        container=container,
                        force=True,
                    )
                cls.config_dir.cleanup()
                raise

        @classmethod
        def tearDownClass(cls):
            for container in cls.dump_logs:
                print("\n\nContainer Logs:")
                print(cls.client.logs(container).decode("utf-8"))
                print()

            for container in cls.containers:
                cls.client.remove_container(
                    container=container,
                    force=True,
                )
            cls.config_dir.cleanup()

        def run(self, result=None):
            # lots of bugs in the dependency libraries at the current versions used
            warnings.filterwarnings("ignore", category=ResourceWarning)
            result = super().run(result) or result
            # Activate log dump if anything didn't succeed
            if len(result.errors) + len(result.failures) > 0:
                self.dump_logs.add(self.repour_container)
            return result

        def check_clone(self, url, tag, expected_files=[]):
            with tempfile.TemporaryDirectory() as repo_dir:
                try:
                    subprocess.check_output(["git", "clone", "--branch", tag, "--", url, repo_dir], stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError as e:
                    print(e.output)
                for expected_file in expected_files:
                    self.assertTrue(
                        expr=os.path.exists(os.path.join(repo_dir, expected_file)),
                        msg="{expected_file} does not exist in internal repository".format(**locals()),
                    )

        def do_pull(self, body, patch=None, expect="ok_pull", expected_files=[]):
            if patch is not None:
                body = body.copy()
                for k,v in patch.items():
                    if v is not None:
                        body[k] = v
            resp = self.requests_session.post(
                url=self.repour_api_url + "/pull",
                json=body,
            )
            ret = resp.json()

            try:
                if expect == "ok_pull":
                    self.assertEqual(resp.status_code, 200)
                    repour.validation.success_pull(ret)
                    self.assertRegex(ret["branch"], "^branch-pull-[0-9a-f]+$")
                    self.assertRegex(ret["tag"], "^repour-[0-9a-f]+$")
                    self.check_clone(
                        url=ret["url"]["readonly"],
                        tag=ret["tag"],
                        expected_files=expected_files,
                    )
                elif expect == "ok_adjust":
                    self.assertEqual(resp.status_code, 200)
                    repour.validation.success_pull_adjust(ret)
                    self.assertRegex(ret["branch"], "^branch-adjust-[0-9a-f]+$")
                    self.assertRegex(ret["tag"], "^repour-[0-9a-f]+$")
                    self.check_clone(
                        url=ret["url"]["readonly"],
                        tag=ret["tag"],
                        expected_files=expected_files,
                    )
                    self.check_clone(
                        url=ret["url"]["readonly"],
                        tag=ret["pull"]["tag"],
                        expected_files=expected_files,
                    )
                elif expect == "validation_error":
                    self.assertEqual(resp.status_code, 400)
                    repour.validation.error_validation(ret)
                elif expect == "described_error":
                    self.assertEqual(resp.status_code, 400)
                    repour.validation.error_described(ret)
                elif expect == "other_error":
                    self.assertEqual(resp.status_code, 500)
                    repour.validation.error_other(ret)
                else:
                    raise Exception("Don't know how to expect {}".format(expect))
            except Exception:
                print("\nResponse Body:")
                print(resp.status_code)
                pprint.pprint(ret)
                print("")
                raise

            return ret

        def test_pull_git(self):
            for ref in ["1.5.0.Beta1", "master", None, "2d8307585e97fff3a86c34eb86c681ba81bb1811"]:
                with self.subTest(ref=ref):
                    self.do_pull(
                        body={
                            "name": "jboss-modules-1.5.0",
                            "type": "git",
                            "url": "https://github.com/jboss-modules/jboss-modules.git",
                        },
                        patch={
                            "ref": ref
                        },
                        expected_files=["pom.xml"],
                    )

        def test_name_capitals(self):
            body = {
                "name": "JGroups",
                "type": "git",
                "ref": "master",
                "url": "https://github.com/belaban/JGroups.git",
            }
            for i in range(2):
                with self.subTest(stage=i):
                    self.do_pull(
                        body=body,
                        expected_files=["pom.xml"],
                    )
            with self.subTest(stage="lowercase"):
                self.do_pull(
                    body=body,
                    patch={
                        "name": body["name"].lower(),
                    },
                    expected_files=["pom.xml"],
                )

        def test_pull_hg(self):
            for ref in ["default", None]:
                with self.subTest(ref=ref):
                    ret = self.do_pull(
                        body={
                            "name": "hello",
                            "type": "hg",
                            "url": "https://selenic.com/repo/hello",
                        },
                        patch={
                            "ref": ref,
                        },
                        expected_files=["Makefile"],
                    )
                    self.assertIn("hello", ret["url"]["readonly"])

        def test_pull_svn(self):
            for ref,suffix in [(None,"tags/commons-io-1.3.2"), ("1709188","trunk")]:
                with self.subTest(ref=ref, suffix=suffix):
                    self.do_pull(
                        body={
                            "name": "apache-commons-io",
                            "type": "svn",
                            "url": "https://svn.apache.org/repos/asf/commons/proper/io/" + suffix,
                        },
                        patch={
                            "ref": ref,
                        },
                        expected_files=["pom.xml"],
                    )

        def test_pull_archive(self):
            for ext in [".tar.gz", ".zip"]:
                with self.subTest(ext=ext):
                    self.do_pull(
                        body={
                            "name": "jboss-modules-1.5.0",
                            "type": "archive",
                            "url": "https://github.com/jboss-modules/jboss-modules/archive/1.4.4.Final" + ext,
                        },
                        expected_files=["pom.xml"],
                    )

        def test_callback(self):
            server_ip = self.client.inspect_container(self.repour_container)["NetworkSettings"]["Gateway"]
            server_port = 8080

            server_done = threading.Event()
            callback_data = None
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    nonlocal callback_data
                    size = int(self.headers.get("content-length", 0))
                    callback_data = json.loads(self.rfile.read(size).decode("utf-8"))
                    self.send_response(200)
                    self.end_headers()
                    self.flush_headers()
                    server_done.set()

                def log_request(self, format, *args):
                    pass

            server = http.server.HTTPServer((server_ip, server_port), Handler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                server_thread.start()
                resp = self.requests_session.post(
                    url=self.repour_api_url + "/pull",
                    json={
                        "name": "jboss-modules",
                        "type": "git",
                        "url": "https://github.com/jboss-modules/jboss-modules.git",
                        "ref": "master",
                        "callback": {
                            "url": "http://{server_ip}:{server_port}/".format(**locals()),
                        },
                    },
                )
                ret = resp.json()
                server_done.wait(timeout=10)
            finally:
                server.shutdown()
                server_thread.join(timeout=5)
            self.assertEqual(200, callback_data["callback"]["status"])
            self.assertEqual(ret["callback"]["id"], callback_data["callback"]["id"])

        # TODO possibly use decorator on adjust tests to skip if PME restURL host isn't accessible
