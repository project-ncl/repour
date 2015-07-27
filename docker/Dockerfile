FROM fedora:22
MAINTAINER Alex Szczuczko <aszczucz@redhat.com>
EXPOSE 7331

RUN dnf install -y bsdtar python3 python3-pip python3-devel python3-Cython libyaml-devel "@Development Tools" java-1.8.0-openjdk && \
    pip3 --no-cache-dir install vex && \
    useradd -rm repour && \
    dnf clean all

USER repour
WORKDIR /home/repour
ENTRYPOINT ["/bin/vex", "rpo", "python", "-m", "repour"]
CMD ["run"]

ADD ["content.tar", "/home/repour/"]

RUN vex -m --python python3.4 rpo pip --no-cache-dir install -r venv-freeze.txt
