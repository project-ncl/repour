#!/usr/bin/env python3

import grp
import os
import pwd
import shutil
import sys

# Minimal workaround for OpenShift's Arbitrary User ID "feature"
# https://docs.openshift.com/enterprise/3.1/creating_images/guidelines.html#use-uid
# Requires nss_wrapper and gettext to be present in the image


def uid_exists(uid):
    try:
        pwd.getpwuid(uid)
    except KeyError as e:
        return False
    else:
        return True


def gid_exists(gid):
    try:
        grp.getgrgid(gid)
    except KeyError as e:
        return False
    else:
        return True


def exec_with_fake_user(cmd):
    # If the the current uid/gid isn't in passwd/group, then apply the nss_wrapper hack
    uid = os.getuid()
    gid = os.getgid()
    uid_present = uid_exists(uid)
    gid_present = gid_exists(gid)

    env = os.environ.copy()
    if not (uid_present and gid_present):
        env["LD_PRELOAD"] = "libnss_wrapper.so"

        # Docker seems to always set HOME to / when forcing a UID/GID.
        if "AU_HOME" in env or "HOME" not in env or env["HOME"] == "/":
            env["HOME"] = env.get("AU_HOME", os.getcwd())

        real_passwd_path = "/etc/passwd"
        fake_passwd_path = "/tmp/passwd"
        if uid_present:
            env["NSS_WRAPPER_PASSWD"] = real_passwd_path
            env["USER"] = pwd.getpwuid(uid).pw_name
        else:
            env["NSS_WRAPPER_PASSWD"] = fake_passwd_path
            env["USER"] = env.get("AU_USERNAME", "default")
            shutil.copy(real_passwd_path, fake_passwd_path)
            with open(fake_passwd_path, "a") as f:
                f.write(
                    "{name}:x:{uid}:{gid}::{home}:{shell}\n".format(
                        name=env.get("AU_USERNAME", "default"),
                        uid=uid,
                        gid=gid,
                        home=env["HOME"],
                        shell=env.get("AU_SHELL", "/bin/sh"),
                    )
                )

        real_group_path = "/etc/group"
        fake_group_path = "/tmp/group"
        if gid_present:
            env["NSS_WRAPPER_GROUP"] = real_group_path
        else:
            env["NSS_WRAPPER_GROUP"] = fake_group_path
            shutil.copy(real_group_path, fake_group_path)
            with open(fake_group_path, "a") as f:
                f.write(
                    "{name}:x:{gid}:\n".format(
                        name=env.get("AU_GROUPNAME", "default"), gid=gid
                    )
                )
    else:
        env["USER"] = pwd.getpwuid(uid).pw_name

    # Replace the current process
    os.execvpe(cmd[0], cmd, env)
    # Will never get here


def main():
    exec_with_fake_user(sys.argv[1:])


if __name__ == "__main__":
    main()
