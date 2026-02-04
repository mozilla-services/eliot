# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Utilities for logging configuration and usage.
"""

import logging
import logging.config

from everett.manager import get_runtime_config, generate_uppercase_key


_IS_LOGGING_SET_UP = False


def set_up_logging(logging_level, debug=False, processname=None):
    """Initialize Python logging configuration.

    Note: This only sets up logging once per process. Additional calls will get ignored.

    :arg logging_level: the level to log at
    :arg debug: whether or not to log to the console in an easier-to-read fashion
    :arg processname: the process name to log

    """
    global _IS_LOGGING_SET_UP
    if _IS_LOGGING_SET_UP:
        return

    processname = processname or "main"

    class AddProcessName(logging.Filter):
        def filter(self, record):
            record.processname = processname
            return True

    dc = {
        "version": 1,
        "disable_existing_loggers": True,
        "filters": {
            "add_processname": {"()": AddProcessName},
        },
        "formatters": {
            "app": {
                "format": "%(asctime)s %(levelname)s - %(processname)s - %(name)s - %(message)s"
            },
            "mozlog": {
                "()": "dockerflow.logging.MozlogFormatter",
                "logger_name": "eliot",
            },
        },
        "handlers": {
            "console": {
                "level": logging.DEBUG,
                "class": "logging.StreamHandler",
                "formatter": "app",
                "filters": ["add_processname"],
            },
            "mozlog": {
                "level": logging.DEBUG,
                "class": "logging.StreamHandler",
                "formatter": "mozlog",
                "filters": ["add_processname"],
            },
        },
        "loggers": {
            "eliot": {"level": logging_level},
            "fillmore": {"level": logging.ERROR},
            "markus": {"level": logging.ERROR},
        },
        "root": {"handlers": ["mozlog"], "level": logging.WARNING},
    }

    if debug:
        # In debug mode (only the local development environment), we log to the console
        # in a human-readable fashion and add a markus logger
        dc["loggers"]["markus"] = {"level": logging.INFO}
        dc["root"]["handlers"] = ["console"]

    logging.config.dictConfig(dc)
    _IS_LOGGING_SET_UP = True


def log_config(logger, config_manager, component):
    """Log configuration for a given component.

    :arg logger: a Python logging logger
    :arg config_manager: an Everett ConfigManager instance
    :arg component: the component with a Config property to log the configuration of

    """
    for ns, key, value, _ in get_runtime_config(config_manager, component):
        # This gets rid of NO_VALUE
        value = value or ""

        # "secret" is an indicator that the value is secret and shouldn't get logged
        if "secret" in key.lower() and value:
            value = "*****"

        full_key = generate_uppercase_key(key, ns).upper()
        logger.info(f"{full_key}={value}")
