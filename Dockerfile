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
ENTRYPOINT ["./pid1.py", "./au.py", "python3", "-m", "repour"]
CMD ["run-container"]

RUN cd / && \
    groupadd -rg 1001 repour && \
    useradd -rm -u 1001 -g repour repour && \
    chmod og+rwx /home/repour/ && \
    echo "tsflags=nodocs" >> /etc/dnf/dnf.conf && \
    dnf install -y bsdtar python3 java-headless git subversion mercurial nss_wrapper gettext && \
    dnf clean all && \
    echo -ne '\n\tStrictHostKeyChecking no\n\tPreferredAuthentications publickey\n\tIdentityFile /mnt/secrets/repour/repour\n\tControlMaster auto\n\tControlPath /tmp/%r@%h-%p\n\tControlPersist 300\n' >> /etc/ssh/ssh_config

COPY ["venv/container.txt", "container/pid1.py", "container/au.py", "/home/repour/"]
RUN pip3 --no-cache-dir install -r container.txt && \
    chmod og+rx *.py && \
    curl -Lo pom-manipulation-cli.jar 'http://ci.commonjava.org:8180/api/hosted/local-deployments/org/commonjava/maven/ext/pom-manipulation-cli/2.2-SNAPSHOT/pom-manipulation-cli-2.2-20160523.165610-5.jar'

USER 1001

COPY ["repour/*.py", "/home/repour/repour/"]
