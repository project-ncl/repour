FROM fedora:22
MAINTAINER Alex Szczuczko <aszczucz@redhat.com>
EXPOSE 7331

RUN groupadd -rg 1000 repour && \
    useradd -rm -u 1000 -g repour repour && \
    dnf install -y bsdtar python3 python3-Cython libyaml java-1.8.0-openjdk-headless git subversion mercurial && \
    dnf clean all && \
    printf '\n\tStrictHostKeyChecking no\n\tPreferredAuthentications publickey\n\tIdentityFile /home/repour/vol/repour.key' >> /etc/ssh/ssh_config

VOLUME ["/home/repour/vol"]
WORKDIR /home/repour
ENTRYPOINT ["python3", "-m", "repour"]
CMD ["-c", "vol/config.yaml", "run"]

COPY ["venv-freeze.txt", "/home/repour/"]
RUN dnf install -y python3-devel libyaml-devel gcc && \
    pip3 --no-cache-dir install -r venv-freeze.txt && \
    dnf remove -y python3-devel libyaml-devel gcc && \
    dnf clean all

USER repour

COPY ["repour/*.py", "/home/repour/repour/"]
