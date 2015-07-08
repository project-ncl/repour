# Repour - Source Repository Management Service

Public code sources are unsuitable for reproducable builds because they often have unstable history. They may also be in many formats. Repor produces stable internal git repositories with branches containing flattened source trees instead of the full history. This meets the requirements for reproducable builds without imposing any behaviours on upstream.

Additionally, the isolated internal branches allow for modifications (version alignment, patches, etc.) to be commited back without comprimising future pulls.

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

Each successful pull call creates a branch in the named internal repository and a tag at its root. Here's a example command to repeatably clone after pulling a tag named "v1.0.0" into repo "testing" with the server using a local repo provider:

    git clone --depth 1 --branch v1.0.0_1436349331_root file:///tmp/repour-test-repos/testing

## Server Setup

### Prerequisites

- Python 3.4.1+
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
