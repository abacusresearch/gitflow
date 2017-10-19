=========================================
GitFlow CLI
=========================================


Requirements
============
* Python >= 3.6
* Git >= 2.9.0


Install
=======
To install for all users, run this script as root::

    ./install.sh

For user-specific installations, login as the respective user and run::

    ./install.sh --user


Branching Model
===============
+---------------------------+---------------------------+---------------------------+---------------------------+
| Type                      | Tags                      | Property commits [1]      | Rebuild after             |
|                           |                           |                           | increment                 |
+===========================+===========================+===========================+===========================+
| Concurrent                |                           | n                         | y [2]                     |
|                           |                           |                           |                           |
+---------------------------+ version/<sem_ver>         +---------------------------+---------------------------+
| Concurrent                | build/<number> (optional) | for all increments                                    |
| + Project Properties      |                           |                                                       |
+---------------------------+---------------------------+---------------------------+---------------------------+
| Sequential                |                           | n                         | for increments other      |
|                           |                           |                           | than pre-release type     |
+---------------------------+                           +---------------------------+---------------------------+
| Sequential                | version/<sem_ver>         | for all increments                                    |
| + Properties              | seq/<number>              |                                                       |
+---------------------------+ build/<number> (optional) +---------------------------+---------------------------+
| Sequential                |                           | for all increments                                    |
| + Properties              |                           | except pre-release-type                               |
| + Opaque                  |                           |                                                       |
+---------------------------+---------------------------+---------------------------+---------------------------+

[1] Release branch tags will never point to commits on master.
A version property commit implies a rebuild of the corresponding hash.
[2] A build process would need to fetch the version information from the project repository.


Configuration
=============
The configuration file is located at the workspace (branch) root and is named `gitflow.json` unless overridden
with `--config=<relative-path>`.


Examples
--------


Android App
~~~~~~~~~~~
::

    {

      "versioningScheme": "semverWithTiedSeq",
      "versionTypes": ["alpha", "beta", "rc"],

      "propertyFile": "project.properties",
      "versionPropertyName": "version",
      "sequentialVersionPropertyName": "androidVersionCode",

      "build": {
        "stages": {
          "assemble": [
            ["./gradlew", "assembleDebug"]
          ],
          "test": [
            ["./gradlew", "test"]
          ],
          "integration-test": [
            ["./gradlew", "connectedDebugAndroidTest"]
          ]
        }
      }

    }


Maven / Android Library Project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    {

      "versioningScheme": "semver",
      "versionTypes": ["alpha", "beta", "rc"],

      "propertyFile": "project.properties",
      "versionPropertyName": "mavenVersion",

      "build": {
        "stages": {
          "assemble": [
            ["./gradlew", "assembleDebug"]
          ],
          "test": [
            ["./gradlew", "test"]
          ],
          "integration-test": [
            ["./gradlew", "connectedDebugAndroidTest"]
          ]
        }
      }

    }


Python Project
~~~~~~~~~~~~~~
::

    {

      "versionTypes": ["alpha", "beta", "rc"],

      "propertyFile": "project.properties",
      "versionPropertyName": "version",
      "sequentialVersionPropertyName": "versionCode",

      "build": {
        "stages": {
          "assemble": [
            ["python3", "setup.py", "sdist", "--formats=gztar"],
            ["python3", "setup.py", "bdist"]
          ],
          "test": [
            ["py.test", "--verbose", "test"]
          ]
        }
      }

    }


Usage
=====
See CLI help::

    git flow -h


Uninstall
=========
Run as the install user::

    ./uninstall.sh
