#!/usr/bin/env python3

import os
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile

# Ensure Gitolite, SSHD, and Apache HTTPD are setup for use in OSE within the
# CWD, and then run SSHD and HTTPD at the same time. Forward signals to both,
# quit after both quit. Pass back logs from both to stdout/stderr.
# See /usr/share/doc/gitolite3/gitolite3-README-fedora
# See https://serverfault.com/questions/344295/is-it-possible-to-run-sshd-as-a-normal-user
# See https://gist.github.com/zroger/5990997
# See https://www.kernel.org/pub/software/scm/git/docs/git-http-backend.html

def do_server_setup():
    # Shouldn't need to change the umask as this is all within the persistent volume, and all the same user

    # Setup gitolite with a temporary admin key
    subprocess.check_call(["ssh-keygen", "-f", "admin", "-N", ""])
    subprocess.check_call(["gitolite", "setup", "-pk", "admin.pub"])
    with os.fdopen(os.open(".ssh/config", os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
        f.write("""Host localhost
    PreferredAuthentications publickey
    IdentityFile ~/admin
    StrictHostKeyChecking no
""")

    # SSHD config
    subprocess.check_call(["ssh-keygen", "-t", "rsa", "-f", "ssh_host_rsa_key", "-N", ""])
    with open("sshd_config", "w") as f:
        f.write("""Port 2222
HostKey {d}/ssh_host_rsa_key
PidFile /tmp/sshd.pid
UsePrivilegeSeparation no
PasswordAuthentication no
""".format(d=os.getcwd()))

    # Apache HTTPD config
    with open("httpd.conf", "w") as f:
        f.write("""Listen 8080
PidFile /tmp/httpd.pid

LoadModule unixd_module /etc/httpd/modules/mod_unixd.so
LoadModule mpm_prefork_module /etc/httpd/modules/mod_mpm_prefork.so
LoadModule cgi_module /etc/httpd/modules/mod_cgi.so
LoadModule authz_core_module /etc/httpd/modules/mod_authz_core.so
LoadModule alias_module /etc/httpd/modules/mod_alias.so
LoadModule mime_module /etc/httpd/modules/mod_mime.so
LoadModule log_config_module /etc/httpd/modules/mod_log_config.so
LoadModule env_module /etc/httpd/modules/mod_env.so

TypesConfig /etc/mime.types
AddDefaultCharset UTF-8

LogLevel warn
ErrorLog "||/bin/cat"
LogFormat "%h %l %u %t '%r' %>s %b" common
CustomLog "||/bin/cat" common

SetEnv GIT_PROJECT_ROOT /var/lib/gitolite3/repositories
SetEnv GIT_HTTP_EXPORT_ALL
ScriptAlias / /usr/libexec/git-core/git-http-backend/
""".format(d=os.getcwd()))

def start_servers():
    sshd_cmd = ["/sbin/sshd", "-f", "./sshd_config", "-D", "-e"]
    sshd_pid = os.spawnvp(os.P_NOWAIT, sshd_cmd[0], sshd_cmd)
    httpd_cmd = ["httpd", "-d", ".", "-f", "httpd.conf", "-DFOREGROUND"]
    httpd_pid = os.spawnvp(os.P_NOWAIT, httpd_cmd[0], httpd_cmd)
    return set((sshd_pid, httpd_pid))

def forward_signals_to(pids):
    def forward_handler(signum, frame):
        for pid in pids:
            try:
                os.kill(pid, signum)
            except ProcessLookupError:
                pass
    for signum in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(signum, forward_handler)

def do_setup():
    # Temporarily clone admin repo to add repour user
    repour_publickey_path = "/mnt/secrets/repour/repour.pub"
    with tempfile.TemporaryDirectory() as d:
        subprocess.check_call([
            "git",
            "clone",
            "ssh://{user}@localhost:2222/gitolite-admin".format(user=pwd.getpwuid(os.getuid()).pw_name),
            d,
        ])
        with open(os.path.join(d, "conf/gitolite.conf"), "a") as f:
            f.write("""
repo CREATOR/..*
    C   = repour
    RW+ = admin
    RW  = CREATOR WRITERS
    R   = @all READERS
""")
        shutil.copy(repour_publickey_path, os.path.join(d, "keydir/repour.pub"))
        for k,v in [("user.name", "admin"), ("user.email", "<>")]:
            subprocess.check_call(["git", "-C", d, "config", "--local", k, v])
        subprocess.check_call(["git", "-C", d, "add", "-A"])
        subprocess.check_call(["git", "-C", d, "commit", "-m", "Add repour"])
        subprocess.check_call(["git", "-C", d, "push"])

    # Change admin key so we don't know the admin's private key
    admin_publickey_path = "/mnt/secrets/admin/admin.pub"
    subprocess.check_call(["gitolite", "setup", "-pk", admin_publickey_path])
    os.remove(".ssh/config")
    os.remove("admin")
    os.remove("admin.pub")

def reap_children(pids):
    first_child_to_quit = True
    overall_status = 0
    while pids:
        try:
            pid, status = os.waitpid(os.P_ALL, 0)
        except InterruptedError as e:
            # Signals are already handled by the children exiting
            pass
        else:
            if pid in pids:
                pids.remove(pid)
                if first_child_to_quit:
                    overall_status = status
                    first_child_to_quit = False
                    for cp in pids:
                        try:
                            os.kill(cp, signal.SIGTERM)
                        except ProcessLookupError as e:
                            pids.remove(cp)
    return overall_status

def setup_then_spawn():
    setup_required = not os.path.exists("sshd_config")
    if setup_required:
        do_server_setup()

    server_pids = start_servers()
    forward_signals_to(server_pids)

    if setup_required:
        do_setup()

    return reap_children(server_pids)

def main():
    sys.exit(setup_then_spawn())

if __name__ == "__main__":
    main()
