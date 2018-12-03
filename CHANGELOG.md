# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased] - <yyyy>-<mm>-<dd>
### Changed

## [1.4.2] - 2018-12-03
### Changed
- [NCL-4285] Syncs where the ref does not exist are now considered User error instead of system error

### Fixed
- [NCL-4231] Fix bug in repour syncing of branches for `/adjust` endpoint


## [1.4.1] - 2018-11-13
### Changed
- [NCL-4248] Use a temporary-settings.xml when aligning temporary builds for plugin injection

## [1.4.0] - 2018-09-25
### Added
- [NCL-4047] Print useful error message when user is trying to sync with a private Github repository without the required permissions

- [NCL-4082] Add endpoint `/git-external-to-internal` to translate external Git repository links into internal Git repository links

- [NCL-4089] Add ability to override default result's groupid/artifactid with custom parameter 'EXECUTION_ROOT_NAME' for the `/adjust` endpoint

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
