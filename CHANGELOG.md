# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- [NCL-4047] Print useful error message when user is trying to sync with a private Github repository without the required permissions

- [NCL-4082] Add endpoint `/git-external-to-internal` to translate external Git repository links into internal Git repository links

### Fixed
- [NCL-4039] Repour does not require a value for `originRepoUrl` on the `/adjust` endpoint if sync is false

### Changed
- [NCL-4069] Handle case with adjust with pre-build-sync on, when ref is present in downstream repository only. In that case, no sync is required


# Template

## [<version>] - <yyyy>-<mm>-<dd>
### Added
- Section

### Changed
- Section

### Deprecated
- Section

### Removed
- Section

### Fixed
- Section

### Security
- Section
