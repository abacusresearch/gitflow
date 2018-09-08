=========================================
GitFlow CLI
=========================================


Requirements
============
* Python >= 3.6
* Git >= 2.9.0


Install
=======

For all users
-------------

Run this script as root::

    ./install.sh

Installation in User Home
-------------------------

Login as the respective user and run::

    ./install.sh --user

Make sure, the installation location of executable python files is present in PATH.
For bash, extend ~/.bash_profile with::

    export PATH="$PATH:$HOME/.local/bin"


Configuration
=============
The configuration file is located at the workspace (branch) root and is named `.gitflow.json` unless overridden
with `--config=<relative-path>`.


Versioning Scheme
-----------------

Branching Model:

* master
* release/{major}.{minor}
* dev/(fix|issue|topic)/(name|issue-id)
* prod/(fix|issue|topic)/(name|issue-id)

Version tags shall never point to commits on master, thus, branches with tags should always be merged without fast forwarding: `git merge --no-ff`.
Branches are created on a per minor version basis.

semver
~~~~~~

* Version specification: `SemVer 2.0 <https://semver.org/spec/v2.0.0.html>`_
* Version format: {major}.{minor}.{patch}[-{prerelease-type}.{prerelease-version}]

Implies rebuilds, when a project is proceeding through testing and delivery stages.

Example Chronology:

1. initial development and release
    *  1.0.0-alpha.1
    *  1.0.0-alpha.2
    *  1.0.0-alpha.3

    *  1.0.0-beta.1 (version increment only)
    *  1.0.0-beta.2

    *  1.0.0-rc.1 (version increment only)
    *  1.0.0-rc.2

    *  1.0.0 (initial major release: version increment only)

2. hotfix:
    *  1.0.1-rc.1

    *  1.0.1 (patch release: version increment only)

3. bugfixing with preliminary beta testing because of extensive or risky fixes:
    *  1.0.2-beta.1
    *  1.0.2-beta.2
    *  1.0.2-beta.3

    *  1.0.2-rc.1 (version increment only)

    *  1.0.2 (patch release: version increment only)

4. development of a new feature, beta testing:
    *  1.1.0-beta.1
    *  1.1.0-beta.2
    *  1.1.0-beta.3

    *  1.1.0-rc.1 (version increment only)
    *  1.1.0-rc.2

    *  1.1.0 (minor release: version increment only)

5. development of a new major version with breaking changes and new features:
    *  2.0.0-alpha.1
    *  2.0.0-alpha.2
    *  2.0.0-alpha.3

    *  ..... 1.0.3 (intermediate patch release for 1.x) .....

    *  2.0.0-beta.1 (version increment only)
    *  2.0.0-beta.2

    *  2.0.0-rc.1 (version increment only)
    *  2.0.0-rc.2

    *  2.0.0-(major release: version increment only)

semverWithSeq
~~~~~~~~~~~~~

* Version specification: `SemVer 2.0 <https://semver.org/spec/v2.0.0.html>`_
* Version format: {major}.{minor}.{patch}-{sequence-number}

Since there are only abstract prerelease versions, there's no need for version increments after testing, or before delivery.
The sequence number applies across all branches of a project. Concurrent versioning is not possible.

Example Chronology:

Testing and delivery is not semantically coupled to the version string.
There are no 'version increment only builds', builds that pass testing can be forwarded to the next step as is.

1. initial development and release
    *  1.0.0-1
    *  1.0.0-2
    *  1.0.0-3

2. hotfix:
    *  1.0.1-5

3. bugfixing:
    *  1.0.2-6
    *  1.0.2-7

4. development of a new feature:
    *  1.1.0-8 (supersedes the 1.0 branch)
    *  1.1.0-9

5. development of a new major version with breaking changes and new features:
    *  2.0.0-10 (supersedes the 1.1 branch)
    *  2.0.0-11
    *  2.0.0-12

Examples
--------


Maven Project
~~~~~~~~~~~~~
::

    {

      "versioningScheme": "semver",
      "releaseTypes": ["alpha", "beta"],

      "onVersionChange": [
        ["mvn", "versions:set", "-DnewVersion=${NEW_VERSION}"]
      ]

    }


or

::

    {

      "versioningScheme": "semver",
      "releaseTypes": ["alpha", "beta"],

      "propertyFile": "project.properties",
      "versionProperty": "mavenVersion"

    }


Android App Project
~~~~~~~~~~~~~~~~~~~
::

    {

      "versioningScheme": "semverWithSeq",

      "propertyFile": "project.properties",
      "versionProperty": "version",
      "sequenceNumberProperty": "androidVersionCode"

    }


Android Library Project
~~~~~~~~~~~~~~~~~~~~~~~
::

    {

      "versioningScheme": "semver",
      "releaseTypes": ["alpha", "beta"],

      "propertyFile": "project.properties",
      "versionProperty": "mavenVersion"

    }


Python Project
~~~~~~~~~~~~~~
::

    {

      "versioningScheme": "semver",
      "releaseTypes": ["alpha", "beta"],

      "propertyFile": "rootmodule/config.ini",
      "versionProperty": "version"

    }


Usage
=====
See CLI help::

    git flow -h


Uninstall
=========
Run as the install user::

    ./uninstall.sh

Development
===========

Install all dependencies::

    pip install -r build_requirements.txt -r requirements.txt -r test_requirements.txt
