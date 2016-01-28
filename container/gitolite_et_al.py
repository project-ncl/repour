#!/usr/bin/env python3

import os
import subprocess
import sys

# Ensure Gitolite, SSHD, and Apache HTTPD are setup for use in OSE within the
# CWD, and then run SSHD and HTTPD at the same time. Forward signals to both,
# quit after both quit or one quits in error. Pass back logs from both to
# stdout/stderr.
# See /usr/share/doc/gitolite3/gitolite3-README-fedora
# See https://serverfault.com/questions/344295/is-it-possible-to-run-sshd-as-a-normal-user

def do_setup():
    # Shouldn't need to change the umask as this is all within the persistent volume, and all the same user
    admin_publickey_path = "/mnt/secrets/admin/admin.pub"
    subprocess.check_call(["gitolite", "setup", "-pk", admin_publickey_path])

    # Temporarily clone admin repo using local as SSHD isn't set up yet
    repour_publickey_path = "/mnt/secrets/repour/repour.pub"
    admin_clone_path = "temp_admin_clone"
    subprocess.check_call(["git", "clone", "repositories/gitolite-admin.git", admin_clone_path])
    # TODO add repour user with RW wild repo permission, public key from secrets mount


    # SSHD config
    subprocess.check_call(["ssh-keygen", "-t", "rsa", "-f", "ssh_host_rsa_key", "-N", ""])
    with ("sshd_config", "w") as f:
        f.write("""Port 2222
HostKey {d}/ssh_host_rsa_key
PidFile /tmp/sshd.pid
UsePrivilegeSeparation no
PasswordAuthentication no
""".format(d=os.getcwd()))

    # Apache HTTPD config
    with ("httpd.conf", "w") as f:
        f.write("""Listen 8080
PidFile /tmp/httpd.pid

LoadModule unixd_module /etc/httpd/modules/mod_unixd.so
LoadModule mpm_prefork_module /etc/httpd/modules/mod_mpm_prefork.so
LoadModule cgi_module /etc/httpd/modules/mod_cgi.so
LoadModule authz_core_module /etc/httpd/modules/mod_authz_core.so
LoadModule authz_host_module /etc/httpd/modules/mod_authz_host.so
LoadModule access_compat_module /etc/httpd/modules/mod_access_compat.so
LoadModule alias_module /etc/httpd/modules/mod_alias.so
LoadModule mime_module /etc/httpd/modules/mod_mime.so
LoadModule log_config_module /etc/httpd/modules/mod_log_config.so

TypesConfig /etc/mime.types
AddDefaultCharset UTF-8

LogLevel warn
ErrorLog "|/bin/cat"
LogFormat "%h %l %u %t \"%r\" %>s %b" common
CustomLog "|/bin/cat" common

ScriptAlias /cgit /var/www/cgi-bin/cgit
<Directory "/var/www/cgi-bin">
    AllowOverride None
    Options +ExecCGI
    Order allow,deny
    Allow from all
</Directory>
Alias /cgit-data /usr/share/cgit
<Directory "/usr/share/cgit">
    Require all granted
</Directory>
""".format(d=os.getcwd()))

# TODO now need to:
# - do gitolite config
# - write sshd and httpd config, with appropriate changes like, setting the ports to 2222/8080, log to stdout only (if possible)
#   - /sbin/sshd -f ./sshd_config -D -e
#   - httpd -d . -f httpd.conf -DFOREGROUND
# - run sshd and apache httpd as children concurrently
# - also get the gitolite logs to stdout somehow, ideally with no local log file, but tail -f that if nothing else
# - forward signals to both
# - quit when both have quit
def setup_then_exec(cmd):
    if not os.path.exists("sshd_config"):
        do_setup()

    # Replace the current process
    os.execvp(cmd[0], cmd)
    # Will never get here

def main():
    setup_then_exec(sys.argv[1:])

if __name__ == "__main__":
    main()
