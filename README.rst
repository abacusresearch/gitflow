=========================================
GitFlow CLI
=========================================

Requirements
~~~~~~~~~~~~
* Python >= 3.0
* Git >= 2.9.0

Install
~~~~~~~
To install for all users, run this script as root::

    ./install.sh

For user-specific installations, login as the respective user and run::

    ./install.sh --user

Branching Model
~~~~~~~~~~~~~~~
+---------------------------+---------------------------+---------------------------+---------------------------+
| Type                      | Tags                      | Property commits [1]      | Rebuild after             |
|                           |                           |                           | increment                 |
+===========================+===========================+===========================+===========================+
| Concurrent                | version/<sem_ver>         | n                         | y [2]                     |
|                           | build/<number> (optional) |                           |                           |
+---------------------------+---------------------------+---------------------------+---------------------------+
| Concurrent                | for all increments          for all increments                                    |
| + Project Properties      |                                                                                   |
+---------------------------+---------------------------+---------------------------+---------------------------+
| Sequential                |                           | n                         | y [2]                     |
|                           |                           |                           |                           |
+---------------------------+                           +---------------------------+---------------------------+
| Sequential                | version/<sem_ver>         | for all increments                                    |
| + Properties              | seq/<number>              |                                                       |
+---------------------------+ build/<number> (optional) +---------------------------+---------------------------+
| Sequential                |                           | for all increments                                    |
| + Properties              |                           | except pre-release-type                               |
| + Opaque                  |                           |                                                       |
+---------------------------+---------------------------+---------------------------+---------------------------+

[1] Hides release branch tags on the development base branch.
Indicates whether a rebuild is necessary after a version increment.
[2] A build process would need to fetch the version information from the project repository.

Configuration
~~~~~~~~~~~~~
The configuration file is located at the workspace (branch) root and is named `gitflow.properties` unless overridden
with `--config=<relative-path>`.

Minimal Example::

    propertyFile=project.properties
    versionPropertyName=mavenPomVersion
    sequentialVersionPropertyName=androidVersionCode

    preReleaseVersionQualifiers=alpha,beta,rc

Usage
~~~~~
See CLI help::

    git flow -h

Uninstall
~~~~~~~~~
Run as the install user::

    ./uninstall.sh
