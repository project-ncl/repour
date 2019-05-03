# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased] - <yyyy>-<mm>-<dd>
### Added
- [NCL-4120] Repour dev mode is added! It'll help with preventing tag collision
             when syncing between internal repositories during testing
- [NCL-4255] Sync everything on the `/clone` endpoint if the internal repository is 'new'
- [NCL-3793] Support for alignment using project-manipulator for NPM projects
- [NCL-4585] Support for alignment using Gradle analyze init plugin for Gradle projects
- [NCL-4250] Python >= 3.5 support

### Removed
- [NCL-3872] `/pull` endpoint and tests

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
