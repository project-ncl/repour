FROM fedora:22
MAINTAINER Alex Szczuczko <aszczucz@redhat.com>
EXPOSE 7331
ENTRYPOINT ["/bin/python3", "-m", "/home/repour/repour"]
CMD ["run"]

RUN dnf install python3 python3-devel python3-Cython libyaml-devel && \
    useradd TODO

ADD ["content.tar", "/home/repour/"]
