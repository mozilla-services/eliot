===========
Development
===========

.. contents::
   :local:


Setup quickstart
================

1. Install required software: Docker, just, and git.

   **Linux**:

       Use your package manager.

   **OSX**:

       Install `Docker for Mac <https://docs.docker.com/docker-for-mac/>`_.

       Use `homebrew <https://brew.sh>`_ to install just and git:

       .. code-block:: shell

          $ brew install just git

   **Other**:

       Install `Docker <https://docs.docker.com/engine/installation/>`_.

       Install `just <https://just.systems/man/en/packages.html>`_.

       Install `git <https://git-scm.com/>`_.

2. Clone the repository so you have a copy on your host machine.

   Instructions for cloning are `on the Eliot page in GitHub
   <https://github.com/mozilla-services/eliot>`_.

3. (*Optional for Linux users*) Set UID and GID for Docker container user.

   If you're on Linux or you want to set the UID/GID of the app user that
   runs in the Docker containers, run:

   .. code-block:: shell

      $ just _env

   Then edit the file and set the ``USE_UID`` and ``USE_GID`` variables. These
   will get used when creating the app user in the base image.

   If you ever want different values, change them in ``.env`` and re-run
   ``just build``.

4. Build Docker images.

   From the root of this repository, run:

   .. code-block:: shell

      $ just build

   That will build the app Docker image required for development.


Eliot consists of a webapp and a disk cache manager.

To run Eliot, do:

.. code-block:: shell

   $ just run


The webapp is at `<http://localhost:8000>`__.

The logs its configuration at startup. You can override any of those
configuration settings in your ``.env`` file.


Bugs / Issues
=============

All bugs are tracked in `Bugzilla <https://bugzilla.mozilla.org/>`_.

Write up a new bug:

https://bugzilla.mozilla.org/enter_bug.cgi?product=Eliot

Please make sure there's a bug for any work you want to do before you do
anything. The conversations in the bug can be enlightening and flesh out
issues.


Code workflow
=============

Bugs
----

Either find a bug to work on or write up a new one.

Assign the bug to yourself.

Work out any questions about the problem, the approach to fix it, and any
additional details by posting comments in the bug comments.


Commits
-------

Commits should be self-contained and tests should pass. If there's outstanding
work to do, note that in the commit.


Pull requests
-------------

Pull request summary should indicate the bug the pull request addresses. Use a hyphen between "bug" and the bug ID(s). For
example::

    bug-nnnnnnn: removed frog from tree class

For multiple bugs fixed within a single pull request, list the bugs out individually. For example::

   bug-nnnnnnn, bug-nnnnnnn: removed frog from tree class

Pull request descriptions should cover at least some of the following:

1. what is the issue the pull request is addressing?
2. why does this pull request fix the issue?
3. how should a reviewer review the pull request?
4. what did you do to test the changes?
5. any steps-to-reproduce for the reviewer to use to test the changes

After creating a pull request, attach the pull request to the relevant bugs.

We use the `rob-bugson Firefox addon
<https://addons.mozilla.org/en-US/firefox/addon/rob-bugson/>`_. If the pull
request has "bug-nnnnnnn: ..." or "bug-nnnnnnn, bug-nnnnnnn: ..." in the summary, then rob-bugson will see that
and create a "Attach this PR to bug ..." link.

Then ask someone to review the pull request. If you don't know who to ask, look
at other pull requests to see who's currently reviewing things.


Code reviews
------------

Pull requests should be reviewed before merging.

Style nits should be covered by linting as much as possible.

Code reviews should review the changes in the context of the rest of the
system.


Landing code
------------

Once the code has been reviewed and all tasks in CI pass, the pull request
author should merge the code.

This makes it easier for the author to coordinate landing the changes with
other things that need to happen like landing changes in another repository,
data migrations, configuration changes, and so on.

We use "Rebase and merge" in GitHub.


Conventions
===========

Git conventions
---------------

First line is a summary of the commit. It should start with the bug number. Use a hyphen between "bug" and the bug ID(s). For example::

   bug-nnnnnnn: summary

For multiple bugs fixed within a single commit, list the bugs out individually. For example::

   bug-nnnnnnn, bug-nnnnnnn: summary

After that, the commit should explain *why* the changes are being made and any
notes that future readers should know for context or be aware of.


Python code conventions
-----------------------

All Python code files should have an MPL v2 header at the top::

  # This Source Code Form is subject to the terms of the Mozilla Public
  # License, v. 2.0. If a copy of the MPL was not distributed with this
  # file, You can obtain one at http://mozilla.org/MPL/2.0/.


We use `ruff <https://docs.astral.sh/ruff/>`_ to reformat Python code.


To lint all the code, do:

.. code-block:: bash

  $ just lint


To reformat all the code, do:

.. code-block:: bash

  $ just lint --fix


HTML/CSS conventions
--------------------

2-space indentation.


Javascript code conventions
---------------------------

2-space indentation.

All JavaScript code files should have an MPL v2 header at the top::

  /*
   * This Source Code Form is subject to the terms of the Mozilla Public
   * License, v. 2.0. If a copy of the MPL was not distributed with this
   * file, You can obtain one at http://mozilla.org/MPL/2.0/.
   */


Managing dependencies
=====================

Python dependencies are maintained in the ``pyproject.toml`` file; ``uv`` keeps
exact versions and build hashes in ``uv.lock``.

Most ``uv`` commands should be run inside the container, which can be done
using ``just uv``. To add a new dependency, you can run:

.. code-block:: shell

   $ just uv add my-new-dependency

Then install the new dependency in the managed virtual environment in the
container, you can run

.. code-block:: shell

   $ just uv sync

If there are problems, it'll tell you.

In some cases, you might want to update the primary and all the secondary
dependencies. To do this, run:

.. code-block:: shell

   $ just uv lock --upgrade

Configuration
=============

Configuration is managed using `everett <https://everett.readthedocs.io/>`__.

See :ref:`configuration-chapter` for Eliot configuration.


Metrics
=======

Metrics are emitted using `markus <https://markus.readthedocs.io/>`__.

Metrics are listed in ``eliot/libmarkus.py``. These can then be used anywhere
in the codebase.

.. code-block:: python

   from eliot.libmarkus import METRICS

and then:

.. code-block:: python

   METRICS.histogram("eliot.symbolicate.frames_count", value=len(frames))


See :ref:`metrics-chapter` for list of metrics emitted by Eliot.


Documentation
=============

Documentation for Eliot is build with `Sphinx <http://www.sphinx-doc.org/>`__
and is available on ReadTheDocs at `<https://mozilla-eliot.readthedocs.io/>`__.

To build the docs, do:

.. code-block:: shell

  $ just docs

Then view ``docs/_build/html/index.html`` in your browser.


Testing
=======

Eliot's tests use the `pytest <https://pytest.org/>`__ test framework.

To run all the tests, do:

.. code-block:: shell

   $ just test

Tests for the Symbolication Service webapp go in ``tests/``.

If you need to run specific tests or pass in different arguments, you can use
the testshell:

.. code-block:: shell

   $ just test-shell
   app@xxx:/app$ pytest

   <pytest output>

   app@xxx:/app$ pytest tests/test_app.py

   <pytest output>


How to
======

How to set up a development container for VS Code
-------------------------------------------------
The repository contains configuration files to build a
`development container <https://containers.dev/>`_ in the `.devcontainer`
directory. If you have the "Dev Containers" extension installed in VS Code, you
should be prompted whether you want to reopen the folder in a container on
startup. You can also use the "Dev containers: Reopen in container" command
from the command palette. The container has all Python requirements installed.
IntelliSense, type checking, code formatting with Ruff and running the tests
from the test browser are all set up to work without further configuration.

VS Code should automatically start the container, but it may need to be built on
first run:

.. code-block:: shell

   $ just build devcontainer

Additionally on mac there is the potential that running git from inside any
container that mounts the current directory to `/app`, such as the development
container, will fail with `fatal: detected dubious ownership in repository at
'/app'`. This is likely related to `mozilla-services/tecken#2872
<https://github.com/mozilla-services/tecken/pull/2872>`_, and can be treated by
running the following command from inside the development container, which will
probably throw exceptions on some git read-only objects that are already owned
by app:app, so that's fine:


.. code-block:: shell

   $ chown -R app:app /app


How to change settings in your local dev environment
----------------------------------------------------
Edit the ``.env`` file and add/remove/change settings. These environment
variables are automatically included by docker compose and just.

If you are using a VS Code development container for other repositories such as
`tecken <https://github.com/mozilla-services/tecken>`_ or
`socorro <https://github.com/mozilla-services/socorro>`_, you may need to
change the default ports exposed by docker compose to avoid conflicts with
similar services, for example:

.. code-block:: shell

   EXPOSE_ELIOT_PORT=8100
   EXPOSE_SENTRY_PORT=8190
   EXPOSE_STATSD_PORT=8181

If you are using a development container for VS Code, you may need to restart
the container to pick up changes:

.. code-block:: shell

   $ just run -d devcontainer

How to upgrade the Python version
---------------------------------

To upgrade Python to a new minor or major version, you need to change the version in
these files:

* ``.devcontainer/Dockerfile``
* ``.github/dependabot.yml``
* ``.python-version``
* ``.readthedocs.yaml``
* ``docker/Dockerfile``
* ``pyproject.toml``
