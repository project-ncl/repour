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
                "gradleAnalyzerPluginInitFilePath": "/opt/repour/analyzer-init.gradle",
                "defaultParameters": [
                    "-DrestURL=http://da.custom.com/da/rest/v-1",
                    "-DrepoRemovalBackup=repositories-backup.xml"
                ]
            }
        }
    }

.. note::
    The ``GRADLE`` key is required to be upper case.

The ``gradleAnalyzerPluginInitFilePath`` specifies the path on local disk to the Gradle init file responsible
for triggering the analyzer plugin. This file should define the Gradle plugin version and location from
where it should be fetched. Examples of working init files can be found on Maven Central for particular plugin versions:
http://central.maven.org/maven2/org/jboss/gm/analyzer/analyzer/

The ``defaultParameters`` specifies default parameters that should be passed to the plugin execution process.

Available ``defaultParameters``:

* ``restURL`` (required) -- URL to Dependency Analyzer (DA) REST interface
* ``repoRemovalBackup`` -- name of the XML file containing repositories that were removed from the build.
