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

