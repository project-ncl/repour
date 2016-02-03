#!/usr/bin/env python3

import os
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import time

# Ensure Gitolite, SSHD, and Apache HTTPD are setup for use in OSE within the
# CWD, and then run SSHD and HTTPD at the same time. Forward signals to both,
# quit after both quit. Pass back logs from both to stdout/stderr.
# See /usr/share/doc/gitolite3/gitolite3-README-fedora
# See https://serverfault.com/questions/344295/is-it-possible-to-run-sshd-as-a-normal-user
# See https://gist.github.com/zroger/5990997
# See https://www.kernel.org/pub/software/scm/git/docs/git-http-backend.html

def do_server_setup():
    print("==> Performing initial server setup", flush=True)
    print("  -> SSHD", flush=True)
    # SSHD config
    subprocess.check_call(["ssh-keygen", "-t", "rsa", "-f", "ssh_host_rsa_key", "-N", ""])
    with open("sshd_config", "w") as f:
        f.write("""Port 2222
HostKey {d}/ssh_host_rsa_key
PidFile /tmp/sshd.pid
UsePrivilegeSeparation no
PasswordAuthentication no
PermitUserEnvironment yes
StrictModes no
""".format(d=os.getcwd()))

    # Apache HTTPD config
    print("  -> Apache HTTPD", flush=True)
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
    print("==> Starting servers", flush=True)
    print("  -> Gitolite Log Tail", flush=True)
    gitolite_log_fifo = "/tmp/gitolite_logs.fifo"
    if not os.path.exists(gitolite_log_fifo):
        os.mkfifo(gitolite_log_fifo)

    os.makedirs(".ssh/", mode=0o700, exist_ok=True)
    with open(".ssh/environment", "w") as f:
        f.write("GL_LOGFILE={gitolite_log_fifo}\n".format(**locals()))
        # SSHD doesn't pass its environment on to gitolite, so the critical
        # nss-wrapper stuff doesn't get through. Fix this.
        for k,v in os.environ.items():
            f.write("{k}={v}\n".format(**locals()))

    tail_cmd = ["tail", "-f", gitolite_log_fifo]
    tail_pid = os.spawnvp(os.P_NOWAIT, tail_cmd[0], tail_cmd)

    print("  -> SSHD", flush=True)
    sshd_cmd = ["/sbin/sshd", "-f", "./sshd_config", "-D", "-e"]
    sshd_pid = os.spawnvp(os.P_NOWAIT, sshd_cmd[0], sshd_cmd)

    print("  -> Apache HTTPD", flush=True)
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
    print("==> Performing initial Gitolite config", flush=True)
    # Setup gitolite with a temporary admin key
    print("  -> Temporary SSH setup", flush=True)
    tempadmin_dir = "/tmp/tempadmin"
    tempadmin_priv = os.path.join(tempadmin_dir, "admin")
    tempadmin_pub = os.path.join(tempadmin_dir, "admin.pub")
    os.mkdir(tempadmin_dir, mode=0o700)
    subprocess.check_call(["ssh-keygen", "-f", tempadmin_priv, "-N", ""])
    gitolite_setup_env = os.environ.copy()
    gitolite_setup_env["GL_LOGFILE"] = "/dev/null"
    subprocess.check_call(["gitolite", "setup", "-pk", tempadmin_pub], env=gitolite_setup_env)
    with os.fdopen(os.open(".ssh/config", os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
        f.write("""Host localhost
    PreferredAuthentications publickey
    IdentityFile {tempadmin_priv}
    StrictHostKeyChecking no
""".format(**locals()))

    # Wait for SSHD to be ready
    print("  -> Waiting for SSHD", flush=True)
    ready = False
    while not ready:
        try:
            conn = socket.create_connection(("localhost", 2222), timeout=10)
        except ConnectionError:
            time.sleep(0.1)
        else:
            conn.close()
            ready = True

    # Temporarily clone admin repo to add repour user
    print("  -> Cloning admin repository", flush=True)
    repour_publickey_path = "/mnt/secrets/repour/repour.pub"
    tempclone = "/tmp/tmpadminclone"
    subprocess.check_call([
        "git",
        "clone",
        "ssh://{user}@localhost:2222/gitolite-admin".format(user=pwd.getpwuid(os.getuid()).pw_name),
        tempclone,
    ])
    with open(os.path.join(tempclone, "conf/gitolite.conf"), "a") as f:
        f.write("""
repo CREATOR/..*
C   = repour
RW+ = admin
RW  = CREATOR WRITERS
R   = @all READERS
""")
    print("  -> Making admin repository changes", flush=True)
    shutil.copy(repour_publickey_path, os.path.join(tempclone, "keydir/repour.pub"))
    for k,v in [("user.name", "admin"), ("user.email", "<>")]:
        subprocess.check_call(["git", "-C", tempclone, "config", "--local", k, v])
    subprocess.check_call(["git", "-C", tempclone, "add", "-A"])
    subprocess.check_call(["git", "-C", tempclone, "commit", "-m", "Add repour"])
    print("  -> Pushing admin repository changes", flush=True)
    subprocess.check_call(["git", "-C", tempclone, "push"])
    shutil.rmtree(tempclone)

    # Change admin key so we don't know the admin's private key
    print("  -> Removing temporary SSH setup", flush=True)
    admin_publickey_path = "/mnt/secrets/admin/admin.pub"
    subprocess.check_call(["gitolite", "setup", "-pk", admin_publickey_path], env=gitolite_setup_env)
    os.remove(".ssh/config")
    shutil.rmtree(tempadmin_dir)

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

    print("==> Ready", flush=True)
    return reap_children(server_pids)

def main():
    sys.exit(setup_then_spawn())

if __name__ == "__main__":
    main()
