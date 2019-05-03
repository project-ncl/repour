Repour adjust providers
========================

Gradle provider
----------------

Gradle provider is used to align dependencies in Gradle projects. What it does is to execute a Gradle init
plugin that is responsible for generating a metadata file with aligned versions. You can find the plugin in the
https://github.com/project-ncl/gradle-manipulator repository, in the ``analyzer`` directory.

When the plugin finishes, a ``manipulation.json`` file is created and pushed to the repository with other changes.

Configuration
^^^^^^^^^^^^^

.. code-block:: json

    {
        "adjust": {
            "GRADLE": {
                "gradleAnalyzerPluginVersion": "1.0.0",
                "gradleAnalyzerPluginLibDir": "/home/goldmann/git/redhat/repour/libs",
                "defaultParameters": [
                    "-Dda.endpoint.url=http://da.custom.com/da/rest/v-1"
                ]
            }
        }
    }

.. note::
    The ``GRADLE`` key is required to be upper case.

The ``gradleAnalyzerPluginVersion`` specifies the plugin version that is required to run the analyze phase.

There are multiple ways how the plugin can be provided. Following options are available:

1. It can be fetched from a custom directory specified as ``gradleAnalyzerPluginLibDir``,
2. It can be fetched from local Maven repository,
3. It can be fetched from Maven Central.

.. warning::
    Currently specifying ``gradleAnalyzerPluginLibDir`` is required. This should be an absolute path
    to a directory where the analyze jar can be found.

    This will be changed in the future versions after the plugin will be published to https://plugins.gradle.org/.

The ``defaultParameters`` key should specify at least ``da.endpoint.url`` which is a URL to Dependency
Analyzer (DA) REST interface.
