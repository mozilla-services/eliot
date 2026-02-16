# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import site
from unittest.mock import ANY

from fillmore.test import diff_structure
from markus.testing import MetricsMock
from werkzeug.test import Client

from eliot.app import get_app, count_sentry_scrub_error


[SITE_PACKAGES] = site.getsitepackages()

# NOTE(willkg): If this changes, we should update it and look for new things that should
# be scrubbed. Use ANY for things that change between tests like timestamps, source code
# data (line numbers, file names, post/pre_context), event ids, build ids, versions,
# etc.
BROKEN_EVENT = {
    "breadcrumbs": {
        "values": [
            {
                "category": "markus",
                "data": {"asctime": ANY, "processname": "tests"},
                "level": "info",
                "message": ANY,
                "timestamp": ANY,
                "type": "log",
            }
        ]
    },
    "contexts": {
        "runtime": {
            "build": ANY,
            "name": "CPython",
            "version": ANY,
        },
        "trace": {
            "parent_span_id": None,
            "span_id": ANY,
            "trace_id": ANY,
        },
    },
    "environment": "production",
    "event_id": ANY,
    "exception": {
        "values": [
            {
                "mechanism": {"handled": False, "type": "eliot"},
                "module": None,
                "stacktrace": {
                    "frames": [
                        {
                            "abs_path": SITE_PACKAGES + "/falcon/app.py",
                            "context_line": ANY,
                            "filename": "falcon/app.py",
                            "function": "__call__",
                            "in_app": False,
                            "lineno": ANY,
                            "module": "falcon.app",
                            "post_context": ANY,
                            "pre_context": ANY,
                        },
                        {
                            "abs_path": "/app/eliot/health_resource.py",
                            "context_line": ANY,
                            "filename": "eliot/health_resource.py",
                            "function": "on_get",
                            "in_app": True,
                            "lineno": ANY,
                            "module": "eliot.health_resource",
                            "post_context": ANY,
                            "pre_context": ANY,
                        },
                    ]
                },
                "type": "Exception",
                "value": "intentional exception",
            }
        ]
    },
    "extra": {"sys.argv": ANY},
    "level": "error",
    "modules": ANY,
    "platform": "python",
    "release": ANY,
    "request": {
        "env": {"SERVER_NAME": "localhost", "SERVER_PORT": "80"},
        "headers": {
            "Host": "localhost",
            "X-Forwarded-For": "[Scrubbed]",
            "X-Real-Ip": "[Scrubbed]",
        },
        "method": "GET",
        "query_string": "",
        "url": "http://localhost/__broken__",
    },
    "sdk": {
        "integrations": [
            "argv",
            "atexit",
            "dedupe",
            "excepthook",
            "logging",
            "modules",
            "stdlib",
            "threading",
        ],
        "name": "sentry.python",
        "packages": [{"name": "pypi:sentry-sdk", "version": ANY}],
        "version": ANY,
    },
    "server_name": "testnode",
    "timestamp": ANY,
    "transaction": "/__broken__",
    "transaction_info": {"source": "route"},
}


def test_sentry_scrubbing(sentry_helper):
    """Test sentry scrubbing configuration

    This verifies that the scrubbing configuration is working by using the /__broken__
    view to trigger an exception that causes Sentry to emit an event for.

    This also helps us know when something has changed when upgrading sentry_sdk that
    would want us to update our scrubbing code or sentry init options.

    This test will fail whenever we:

    * update sentry_sdk to a new version
    * update Falcon to a new version that somehow adjusts the callstack for an exception
      happening in view code
    * update configuration which will changing the logging breadcrumbs

    In those cases, we should copy the new event, read through it for new problems, and
    redact the parts that will change using ANY so it passes tests.

    """
    client = Client(get_app())

    with sentry_helper.reuse() as sentry_client:
        resp = client.get(
            "/__broken__",
            headers=[
                ("X-Forwarded-For", "forabcde"),
                ("X-Real-Ip", "forip"),
            ],
        )
        assert resp.status_code == 500

        (event,) = sentry_client.envelope_payloads

        # Drop the "_meta" bit because we don't want to compare that.
        del event["_meta"]

        differences = diff_structure(event, BROKEN_EVENT)
        assert differences == []


def test_count_sentry_scrub_error():
    with MetricsMock() as metricsmock:
        metricsmock.clear_records()
        count_sentry_scrub_error("foo")
        metricsmock.assert_incr(
            "eliot.sentry_scrub_error",
            value=1,
            tags=["service:webapp", "host:testnode"],
        )
