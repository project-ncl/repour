import io
import os
import pprint
import shutil
import subprocess
import tempfile
import unittest
import urllib.parse

import yaml

try:
    import docker
    import requests
    import requests_oauthlib
    import oauthlib.oauth2
    deps_available=True
except ImportError:
    deps_available=False

import repour.validation

# Only run integration tests if able and requested
run_integration_tests = deps_available and "REPOUR_RUN_IT" in os.environ

#
# Docker Utils
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
    class TestGitLabIntegration(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            # current file is in test/ relative to repo root
            repo_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

            # Docker client
            cls.client = docker.Client(version="1.19")

            # Build main image
            repour_it_image = "repour_integration_test"
            # Using list to drain the log stream (don't care about it)
            list(cls.client.build(
                path=repo_root,
                rm=True,
                forcerm=True,
                tag=repour_it_image,
            ))

            # Create repour volume dir
            cls.config_dir = tempfile.TemporaryDirectory()

            # Create key pair
            rkp = os.path.join(cls.config_dir.name, "repour")
            subprocess.check_call(["ssh-keygen", "-f", rkp, "-N", ""])
            os.rename(rkp, os.path.join(cls.config_dir.name, "repour.key"))
            with open(os.path.join(cls.config_dir.name, "repour.pub"), "r") as f:
                repour_public_key = f.read().strip()

            # Download PME jar
            r = requests.get(
                url="http://central.maven.org/maven2/org/commonjava/maven/ext/pom-manipulation-cli/1.7/pom-manipulation-cli-1.7.jar",
                stream=True,
            )
            r.raise_for_status()
            with open(os.path.join(cls.config_dir.name, "pom-manipulation-cli.jar"), "wb") as f:
                shutil.copyfileobj(r.raw, f)

            # Inital repour config, to be updated once GitLab is configured
            repour_config = {
                "log": {
                    "path": "/home/repour/vol/server.log",
                    "level": "DEBUG",
                },
                "bind": {
                    "address": None,
                    "port": 7331,
                },
                "repo_provider": {
                    "type": "gitlab",
                    "params": {
                        "root_url": "http://gitlab:80",
                        "ssh_root_url": "ssh://git@gitlab:22",
                        "group": {
                            "id": None,
                            "name": "mw-build",
                        },
                        "username": "repour",
                        "password": "pa$$w0rd",
                    },
                },
                "adjust_provider": {
                    "type": "subprocess",
                    "params": {
                        "description": "PME",
                        "cmd": [
                            "java",
                            "-jar",
                            "/home/repour/vol/pom-manipulation-cli.jar",
                            "-s",
                            "settings.xml",
                            "-d",
                            "-DrestURL=http://10.19.208.25:8180/da/rest/v-0.2/reports/lookup/gav",
                            "-Dversion.incremental.suffix=redhat",
                            "-DstrictAlignment=true",
                        ],
                    },
                },
            }

            cls.containers = []
            try:
                # TODO could the large gitlab startup time be skipped by persisting/caching the container and repour config dir?
                # Pull/create/start GitLab
                cls.gitlab_port = 54421
                docker_image = "docker.io/gitlab/gitlab-ce:8.0.4-ce.1"
                cls.client.pull(docker_image)
                gitlab_container = cls.client.create_container(
                    image=docker_image,
                    detach=True,
                    host_config=cls.client.create_host_config(
                        port_bindings={
                            80: ("127.0.0.1", cls.gitlab_port)
                        },
                    ),
                )["Id"]
                cls.containers.append(gitlab_container)
                cls.client.start(gitlab_container)
                wait_in_logs(cls.client, gitlab_container, "master process ready")

                # Setup requests for GitLab OAuth
                cls.gitlab_url="http://localhost:{cls.gitlab_port}".format(**locals())
                cls.gitlab_api_url="{cls.gitlab_url}/api/v3".format(**locals())
                cls.gitlab = requests_oauthlib.OAuth2Session(
                    client=oauthlib.oauth2.LegacyApplicationClient(
                        client_id="",
                    ),
                )
                # Disable InsecureTransportError
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
                cls.gitlab.fetch_token(
                    token_url="{cls.gitlab_url}/oauth/token".format(**locals()),
                    username="root",
                    password="5iveL!fe",
                )

                # Configure GitLab
                # Create repour user
                r = cls.gitlab.post(
                    url=cls.gitlab_api_url + "/users",
                    data={
                        "email": "repour@localhost.local",
                        "password": repour_config["repo_provider"]["params"]["password"],
                        "username": repour_config["repo_provider"]["params"]["username"],
                        "name": "Repour",
                        "confirm": "false",
                    },
                )
                r.raise_for_status()
                cls.gitlab_repour_uid = r.json()["id"]

                # Add ssh key to repour user
                r = cls.gitlab.post(
                    url="{cls.gitlab_api_url}/users/{cls.gitlab_repour_uid}/keys".format(**locals()),
                    data={
                        "title": "main",
                        "key": repour_public_key,
                    }
                )
                r.raise_for_status()

                # Create group
                r = cls.gitlab.post(
                    url="{cls.gitlab_api_url}/groups".format(**locals()),
                    data={
                        "name": repour_config["repo_provider"]["params"]["group"]["name"],
                        "path": repour_config["repo_provider"]["params"]["group"]["name"],
                        "description": "Build sources",
                    }
                )
                r.raise_for_status()
                cls.gitlab_gid = r.json()["id"]
                repour_config["repo_provider"]["params"]["group"]["id"] = cls.gitlab_gid

                # Add repour user to group
                r = cls.gitlab.post(
                    url="{cls.gitlab_api_url}/groups/{cls.gitlab_gid}/members".format(**locals()),
                    data={
                        "user_id": cls.gitlab_repour_uid,
                        "access_level": "50",
                    }
                )
                r.raise_for_status()

                # Write repour config
                with open(os.path.join(cls.config_dir.name, "config.yaml"), "w") as f:
                    yaml.dump(repour_config, f)

                # Create/start Repour
                # TODO use constant container name (ex: repour_integration_test_repour)?
                cls.repour_port = 54422
                cls.repour_api_url="http://localhost:{cls.repour_port}".format(**locals())
                repour_container = cls.client.create_container(
                    image=repour_it_image,
                    detach=True,
                    host_config=cls.client.create_host_config(
                        links={ gitlab_container: "gitlab" },
                        binds={
                            cls.config_dir.name: {
                                "bind": "/home/repour/vol",
                                "mode": "z",
                            }
                        },
                        port_bindings={
                            7331: ("127.0.0.1", cls.repour_port)
                        },
                    ),
                )["Id"]
                cls.containers.append(repour_container)
                cls.client.start(repour_container)
                cls.repour_container = repour_container
                wait_in_logs(cls.client, repour_container, "Server started on socket")

                # For run(s) to activate the log dumper in tearDownClass
                cls.dump_logs = set()
            except Exception:
                for container in cls.containers:
                    cls.client.remove_container(
                        container=container,
                        force=True,
                    )
                cls.config_dir.cleanup()
                raise

        @classmethod
        def tearDownClass(cls):
            cls.gitlab.close()

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
            result = super().run(result) or result
            # Activate log dump if anything didn't succeed
            if len(result.errors) + len(result.failures) > 0:
                self.dump_logs.add(self.repour_container)
            return result

        def check_clone(self, url, tag, expected_files=[]):
            # Replace host in returned url
            url = urllib.parse.urlunparse(urllib.parse.urlparse(url)._replace(netloc="localhost:{}".format(self.gitlab_port)))

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
            resp = self.gitlab.post(
                url=self.repour_api_url + "/pull",
                json=body,
            )
            ret = resp.json()

            try:
                if expect == "ok_pull":
                    self.assertEqual(resp.status_code, 200)
                    repour.validation.success_pull(ret)
                    self.assertRegex(ret["branch"], "^pull-[0-9]+$")
                    self.assertRegex(ret["tag"], "^pull-[0-9]+-root$")
                    self.check_clone(
                        url=ret["url"]["readonly"],
                        tag=ret["tag"],
                        expected_files=expected_files,
                    )
                elif expect == "ok_adjust":
                    self.assertEqual(resp.status_code, 200)
                    repour.validation.success_pull_adjust(ret)
                    self.assertRegex(ret["branch"], "^adjust-[0-9]+$")
                    self.assertRegex(ret["tag"], "^adjust-[0-9]+-root$")
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
                ret = self.do_pull(
                    body=body,
                    patch={
                        "name": body["name"].lower(),
                    },
                    expect="described_error",
                )
                self.assertIn("already been allocated", ret["desc"])

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
            for ref,suffix in [(None,"tags/commons-io-2.5"), ("1709188","trunk")]:
                with self.subTest(ref=ref, suffix=suffix):
                    self.do_pull(
                        body={
                            "name": "apache-commons-io",
                            "type": "svn",
                            "url": "https://svn.apache.org/viewvc/commons/proper/io/" + suffix,
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

        # TODO possibly use decorator on adjust tests to skip if PME restURL host isn't accessible
