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

Make sure, that the installation location of executable python files is present in PATH.
For bash, extend ~/.bash_profile with::

    export PATH="$PATH:$HOME/.local/bin"


Uninstall
=========
Run as the install user::

    ./uninstall.sh


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

Version tags shall never point to commits on master, thus, branches with tags should always be merged without fast forwarding:

    `git merge/pull --no-ff ...`

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

The sequence number must be unique across the whole repository. Concurrent versioning on release branches is not (yet) supported.

Since the version is always an abstract prerelease, it does not say anything specific about quality.
Because of that, there's no need for version increments after testing or before delivery.
Builds that pass testing or any other stage, can be forwarded to the next stage as is.
This eliminates risks associated with untested "version increment only" builds or redundant testing of such builds.

This scheme is especially suited for projects, where artifacts are rolled out through multiple, consecutive channels, such as alpha, beta, stable.

Example Chronology:

1. initial development and stable release
    *  1.0.0-1      release: roll out through channels alpha/beta, testing
    *  1.0.0-2      "
    *  1.0.0-3      "
    *  1.0.0-4      release: roll out through channels alpha -> beta -> stable

2. hotfix:
    *  1.0.1-5      release: roll out to the stable channel

3. bugfixing:
    *  1.0.2-6      release: roll out through channels alpha/beta, testing
    *  1.0.2-7      release: roll out through channels alpha and/or beta to stable

4. development of a new feature:
    *  1.1.0-8      release: roll out through channels alpha/beta, testing, supersedes the 1.0 branch
    *  1.1.0-9      release: roll out through channels alpha -> beta -> stable

5. development of a new major version with breaking changes and new features:
    *  2.0.0-10     release: roll out through channels alpha/beta, testing, supersedes the 1.1 branch
    *  2.0.0-11     "
    *  2.0.0-12     release: roll out through channels alpha -> beta -> stable

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


Android App (Gradle)
~~~~~~~~~~~~~~~~~~~~
::

    {

      "versioningScheme": "semverWithSeq",

      "propertyFile": "project.properties",
      "versionProperty": "version",
      "sequenceNumberProperty": "androidVersionCode"

    }


Gradle, Android Library Project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
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


API Project
~~~~~~~~~~~
::

    {

      "versioningScheme": "canonical_datetime",

      "propertyFile": "rootmodule/config.ini",
      "versionProperty": "version"

    }


Usage
=====
See CLI help::

    git flow -h

Development
===========

Install all dependencies::

    pip install -r build_requirements.txt -r requirements.txt -r test_requirements.txt

Update all dependencies:

    python -m pur -r build_requirements.txt -r requirements.txt -r test_requirements.txt
