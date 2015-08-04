# Repour - Archival Code Service

Repour archives source code and any adjustments made to it.

Repour can support any origin format that produces a file tree (git, svn, tar archive, etc.). Each "pulled" tree is converted into an orphan branch in an internal git repository. The internal repository is assumed to be history protected (no force-push allowed), but no such requirements are imposed on the origin.

Each archived tree may optionally be "adjusted", making changes that are commited to the internal branch. The adjust operation can be done as part of a pull operation to increase efficiency.

Why the name "Repour"? First, it contains the common short word for "repository" ("repo"); second, the action of "repouring" could be used to describe what the program does to the repositories.

## Interface

### `/pull`

Run pull operation

#### Request

- Method: `POST`
- Content-Type: `application/json`
- Body (SCM):
```
{
    "name": str,
    "type": str,
    "tag": str,
    "url": Url
}
```
```
{
    "name": "example",
    "type": "git",
    "tag": "teiid-parent-8.11.0.Final",
    "url": "git@github.com:teiid/teiid.git",
}
```
- Body (Archive):
```
{
    "name": str,
    "type": str,
    "url": Url
}
```
```
{
    "name": "example",
    "type": "archive",
    "url": "https://github.com/teiid/teiid/archive/teiid-parent-8.11.0.Final.tar.gz"
}
```

#### Response

- Content-Type: `application/json`
- Status (Success): 200
- Body (Success):
```
{
    "branch": str,
    "tag": str,
    "url": Url
}
```
```
{
    "branch": "teiid-parent-8.11.0.Final_1436360795",
    "tag": "teiid-parent-8.11.0.Final_1436360795_root",
    "url": "file:///tmp/repour-test-repos/example"
}
```
- Status (Invalid request body): 400
- Body (Invalid request body):
```
[
    {
        "error_message": str,
        "error_type": str,
        "path": [str]
    }
]
```
```
[
    {
        "error_message": "expected a URL",
        "error_type": "dictionary value",
        "path": ["url"]
    },
    {
        "error_message": "expected str",
        "error_type": "dictionary value",
        "path": ["name"]
    }
]
```
- Status (Processing error): 400
- Body (Processing error):
```
{
    "desc": str,
    "error_type": str
}
```
```
{
    "desc": "Could not clone with git",
    "error_type": "PullCommandError",
    "cmd": [
        "git",
        "clone",
        "--branch",
        "teiid-parent-8.11.0.Final",
        "--depth",
        "1",
        "--",
        "git@github.com:teiid/teiid.gitasd",
        "/tmp/tmppizdwfsigit"
    ],
    "exit_code": 128
}
```

### Cloning from created repositories

Each successful operation creates a branch in the named repository with a tag at its root. Here's an example git command to clone the `testing` repository after a pull operation returns:

    git clone --branch pull-1436349331-root file:///tmp/repour-test-repos/testing

The server in this case is configured to use the `local` repo provider.

## Server Setup

### Prerequisites

- Python 3.4.1+
- Git 2.4.3+
- pip

### Setup the virtual environment with vex

1. Install vex for the current user with `pip3 install --user vex`
2. Ensure `$PATH` includes `$HOME/.local/bin`
3. Install the required C libraries with system package manager.
4. `vex -m --python python3.4 rpo pip install -r venv-freeze.txt`

On Fedora step three is:

    dnf install python3-devel python3-Cython libyaml-devel

#### Recreating the virtual environment

1. Delete the old environment with `vex -r rpo true`
2. Rerun the last command in the parent section, above.

### Configure

Copy the example configuration in `config-example.yaml` to `config.yaml`, then edit.

### Start the server

    vex rpo python -m repour run

For more information, add the `-h` switch to the command.

## License

The content of this repository is released under the ASL 2.0, as provided in the LICENSE file. See the NOTICE file for the copyright statement and a list of contributors. By submitting a "pull request" or otherwise contributing to this repository, you agree to license your contribution under the license identified above.
