# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Holds the EliotApp code. EliotApp is a WSGI app implemented using Falcon.
"""

import logging
import logging.config
from pathlib import Path
import socket
import sys

from everett.manager import (
    ConfigManager,
    ConfigOSEnv,
    get_config_for_class,
    ListOf,
    Option,
)
import falcon
from falcon.errors import HTTPInternalServerError
from fillmore.libsentry import set_up_sentry
from fillmore.scrubber import Scrubber, Rule, SCRUB_RULES_DEFAULT
import sentry_sdk
from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
from sentry_sdk.utils import event_from_exception

from eliot.cache import DiskCache
from eliot.downloader import SymbolFileDownloader
from eliot.health_resource import (
    BrokenResource,
    HeartbeatResource,
    LBHeartbeatResource,
    VersionResource,
)
from eliot.libdockerflow import get_release_name
from eliot.liblogging import set_up_logging, log_config
from eliot.libmarkus import set_up_metrics, METRICS
from eliot.symbolicate_resource import SymbolicateV4, SymbolicateV5


LOGGER = logging.getLogger(__name__)
REPOROOT_DIR = str(Path(__file__).parent.parent)
STATICROOT_DIR = str(Path(__file__).parent / "static")


# Set up Sentry to scrub infrastructure secrets and the user's IP address.

SCRUB_RULES_ELIOT = [
    Rule(
        path="request.headers",
        keys=["X-Forwarded-For", "X-Real-Ip"],
        scrub="scrub",
    ),
]


def count_sentry_scrub_error(msg):
    METRICS.incr("sentry_scrub_error", value=1, tags=["service:webapp"])


def configure_sentry(app_config):
    scrubber = Scrubber(
        rules=SCRUB_RULES_DEFAULT + SCRUB_RULES_ELIOT,
        error_handler=count_sentry_scrub_error,
    )
    set_up_sentry(
        sentry_dsn=app_config("secret_sentry_dsn"),
        release=get_release_name(REPOROOT_DIR),
        host_id=app_config("hostname"),
        before_send=scrubber,
        # Disable frame-local variables
        include_local_variables=False,
    )


def build_config_manager():
    """Build and return an Everett ConfigManager

    :returns: everett.ConfigManager

    """
    config = ConfigManager(
        environments=[
            # Pull configuration from environment variables
            ConfigOSEnv()
        ],
        doc=(
            "For configuration help, see "
            + "https://mozilla-eliot.readthedocs.io/en/latest/"
        ),
    )
    return config.with_namespace("eliot")


class IndexResource:
    def __init__(self, staticroot_dir):
        self.staticroot_dir = staticroot_dir
        self.data = (Path(self.staticroot_dir) / "index.html").read_text()

    def on_get(self, req, resp):
        METRICS.incr("pageview", tags=["path:/", "method:get"])
        resp.content_type = falcon.MEDIA_HTML
        resp.status = falcon.HTTP_200
        resp.text = self.data


class EliotApp(falcon.App):
    """Falcon App for Eliot."""

    class Config:
        local_dev_env = Option(
            default="False",
            parser=bool,
            doc="Whether or not this is a local development environment.",
            alternate_keys=["root:local_dev_env"],
        )
        hostname = Option(
            default=str(socket.gethostname()),
            doc=(
                "Unique identifier for the host that is running Eliot. This is used "
                "in logging and metrics. The default is socket.gethostname()."
            ),
            alternate_keys=["root:hostname"],
        )
        logging_level = Option(
            default="INFO",
            doc="The logging level to use. DEBUG, INFO, WARNING, ERROR or CRITICAL",
        )
        statsd_host = Option(default="localhost", doc="Hostname for statsd server.")
        statsd_port = Option(default="8124", doc="Port for statsd server.", parser=int)
        secret_sentry_dsn = Option(
            default="",
            doc=(
                "Sentry DSN to use. If this is not set an unhandled exception logging "
                "middleware will be used instead. "
                "See https://docs.sentry.io/quickstart/#configure-the-dsn for details."
            ),
        )
        symbols_cache_dir = Option(
            default="/tmp/cache",
            doc="Location for caching symcache files.",
        )
        symbols_urls = Option(
            default="https://symbols.mozilla.org/try/",
            doc="Comma-separated list of urls to pull symbols files from.",
            parser=ListOf(str),
        )

    def __init__(self, config_manager):
        cors_middleware = falcon.CORSMiddleware(
            allow_origins="*",
            expose_headers=[
                "accept",
                "accept-encoding",
                "authorization",
                "content-type",
                "dnt",
                "origin",
                "user-agent",
                "x-csrftoken",
                "x-requested-with",
            ],
        )

        super().__init__(middleware=cors_middleware)
        self.config_manager = config_manager
        self.config = config_manager.with_options(self)
        self._all_resources = {}

    def set_up(self):
        LOGGER.info("Repository root: %s", REPOROOT_DIR)

        # Set up uncaught error handler
        self.add_error_handler(Exception, self.uncaught_error_handler)

        # Log application configuration
        log_config(LOGGER, self.config_manager, self)

        # Set up metrics
        set_up_metrics(
            statsd_host=self.config("statsd_host"),
            statsd_port=self.config("statsd_port"),
            hostname=self.config("hostname"),
            debug=self.config("local_dev_env"),
        )

        # Set up cachedir and tmpdir
        cachedir = Path(self.config("symbols_cache_dir")).resolve()
        cachecachedir = cachedir / "cache"
        cachecachedir.mkdir(parents=True, exist_ok=True)
        tmpdir = cachedir / "tmp"
        tmpdir.mkdir(parents=True, exist_ok=True)

        self.add_route("version", "/__version__", VersionResource(REPOROOT_DIR))
        self.add_route("heartbeat", "/__heartbeat__", HeartbeatResource())
        self.add_route("lbheartbeat", "/__lbheartbeat__", LBHeartbeatResource())
        self.add_route("broken", "/__broken__", BrokenResource())

        diskcache = DiskCache(cachedir=cachecachedir, tmpdir=tmpdir)
        downloader = SymbolFileDownloader(self.config("symbols_urls"))
        self.add_route(
            "symbolicate_v4",
            "/symbolicate/v4",
            SymbolicateV4(downloader=downloader, cache=diskcache, tmpdir=tmpdir),
        )
        self.add_route(
            "symbolicate_v5",
            "/symbolicate/v5",
            SymbolicateV5(downloader=downloader, cache=diskcache, tmpdir=tmpdir),
        )

        # Add the index.html resource and static route last
        self.add_route("index", "/", IndexResource(STATICROOT_DIR))
        self.add_static_route("/static/", STATICROOT_DIR)

    def add_route(self, name, uri_template, resource, *args, **kwargs):
        """Add specified Falcon route.

        :arg str name: friendly name for this route; use alphanumeric characters

        :arg str url_template: Falcon url template for this route

        :arg obj resource: Falcon resource to handl this route

        """
        self._all_resources[name] = resource
        super().add_route(uri_template, resource, *args, **kwargs)

    def get_resource_by_name(self, name):
        """Return registered resource with specified name.

        :arg str name: the name of the resource to get

        :raises KeyError: if there is no resource by that name

        """
        return self._all_resources[name]

    def get_resources(self):
        """Return a list of registered resources."""
        return self._all_resources.values()

    def uncaught_error_handler(self, req, resp, ex, params):
        """Handle uncaught exceptions

        Falcon calls this for exceptions that don't subclass HTTPError. We want
        to log an exception, then kick off Falcon's internal error handling
        code for the HTTP response.

        """
        # NOTE(willkg): we might be able to get rid of the sentry event capture if the
        # FalconIntegration in sentry-sdk gets fixed
        with sentry_sdk.new_scope() as scope:
            # The SentryWsgiMiddleware tacks on an unhelpful transaction value which
            # makes things hard to find in the Sentry interface, so we stomp on that
            # with the req.path
            scope.transaction.name = req.path

            event, hint = event_from_exception(
                ex,
                client_options=scope.get_client().options,
                mechanism={"type": "eliot", "handled": False},
            )

            event["transaction"] = req.path
            scope.capture_event(event, hint=hint)

        LOGGER.error("Unhandled exception", exc_info=sys.exc_info())
        self._compose_error_response(req, resp, HTTPInternalServerError())

    def verify(self):
        """Verify that Eliot is ready to start."""

    def verify_configuration(self):
        """Verify configuration by accessing each item

        This will raise a configuration error if something isn't right.

        """
        for key in get_config_for_class(self.__class__).keys():
            self.config(key)


def get_app(config_manager=None):
    """Build and return EliotApp instance.

    :arg config_manager: Everet ConfigManager to use; if None, it will build one

    :returns: EliotApp instance

    """
    if config_manager is None:
        config_manager = build_config_manager()

    # Set up logging and sentry first, so we have something to log to. Then
    # build and log everything else.
    app_config = config_manager.with_options(EliotApp)
    set_up_logging(
        logging_level=app_config("logging_level"),
        debug=app_config("local_dev_env"),
        processname="webapp",
    )

    configure_sentry(app_config)

    # Create the app and verify configuration
    app = EliotApp(config_manager)
    app.verify_configuration()
    app.set_up()
    app.verify()

    if app.config("local_dev_env"):
        LOGGER.info("Eliot is running! http://localhost:8000")

    # Wrap app in Sentry WSGI middleware which builds the request section in the
    # Sentry event
    app = SentryWsgiMiddleware(app)

    return app
