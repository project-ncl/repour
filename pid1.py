#!/usr/bin/env python3

import errno
import os
import signal
import sys

# Minimal PID 1 to work around Docker zombie problem, features:
# - Starts one child process as PID 2
# - Reaps adopted zombies while running
# - Passes signals through to the child
# - Exits after the child exists
# - Kills/reaps everything before exiting

def kill_all(pid2, timeout=5):
    pid2_status = None
    # SIGTERM everything but us
    os.kill(os.P_ALL, signal.SIGTERM)
    # Setup SIGALRM timeout
    def handle_timeout(signum, frame):
        raise TimeoutError()
    prev_handler = signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(timeout)
    # Reap all children
    try:
        pid2_status = reap_children(pid2, reap_all=True)
    except TimeoutError as e:
        # SIGKILL everything but us
        os.kill(os.P_ALL, signal.SIGKILL)
    finally:
        # Clean up SIGALRM timeout
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev_handler)
    return pid2_status

def reap_children(pid2, reap_all):
    pid2_status = None
    more_children = True
    while more_children:
        try:
            pid, status = os.waitpid(os.P_ALL, 0)
            if pid == pid2:
                pid2_status = status
                # Exit now if we're not waiting for everything
                if not reap_all:
                    more_children = False
        except ChildProcessError as e:
            if e.errno == errno.ECHILD:
                more_children = False
            else:
                raise
    return pid2_status

def forward_signals_to(pid):
    def forward_handler(signum, frame):
        os.kill(pid, signum)
    for signum in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(signum, forward_handler)

def spawn_pid2(cmd):
    pid2_status = None
    try:
        pid2 = os.spawnvp(os.P_NOWAIT, cmd[0], cmd)
        forward_signals_to(pid2)
        # Wait for pid2 to finish, reaping adopted zombies until then
        pid2_status = reap_children(pid2, reap_all=False)
    finally:
        # If pid2 has already terminated, pid2_status contains the status,
        # otherwise pid2_term_status will capture its status.
        pid2_term_status = kill_all(pid2)
    return pid2_term_status or pid2_status

def main():
    sys.exit(spawn_pid2(sys.argv[1:]))

if __name__ == "__main__":
    main()
