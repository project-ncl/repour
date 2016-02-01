FROM fedora:23
MAINTAINER Alex Szczuczko <aszczucz@redhat.com>

EXPOSE 7331

LABEL io.k8s.description="Archival code service" \
      io.k8s.display-name="Repour" \
      io.openshift.expose-services="7331:http" \
      io.openshift.tags="repour" \
      io.openshift.wants="gitolite" \
      io.openshift.min-cpu="1" \
      io.openshift.min-memory="64Mi"

WORKDIR /home/repour
ENTRYPOINT ["./pid1.py", "python3", "-m", "repour"]
CMD ["run-container"]

RUN cd / && \
    groupadd -rg 1001 repour && \
    useradd -rm -u 1001 -g repour repour && \
    chmod og+rwx /home/repour/ && \
    echo "tsflags=nodocs" >> /etc/dnf/dnf.conf && \
    dnf install -y bsdtar python3 java-headless git subversion mercurial && \
    dnf clean all && \
    printf '\n\tStrictHostKeyChecking no\n\tPreferredAuthentications publickey\n\tIdentityFile /mnt/secrets/repour/repour\n\tControlMaster auto\n\tControlPath /tmp/%r@%h-%p\n\tControlPersist 300\n' >> /etc/ssh/ssh_config

COPY ["venv/container.txt", "container/pid1.py", "/home/repour/"]
RUN pip3 --no-cache-dir install -r container.txt && \
    chmod og+rx *.py && \
    curl -Lo pom-manipulation-cli.jar 'http://central.maven.org/maven2/org/commonjava/maven/ext/pom-manipulation-cli/1.9.2/pom-manipulation-cli-1.9.2.jar'

USER 1001

COPY ["repour/*.py", "/home/repour/repour/"]
