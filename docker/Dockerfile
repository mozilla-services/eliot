# NOTE(smarnach): To upgrade Python to a new minor or major version, see
# https://mozilla-eliot.readthedocs.io/en/latest/dev.html#how-to-upgrade-the-python-version
FROM --platform=linux/amd64 python:3.11.14-slim-bookworm@sha256:2c5bc243b1cc47985ee4fb768bb0bbd4490481c5d0897a62da31b7f30b7304a7

ARG userid=10001
ARG groupid=10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/ \
    PORT=8000

EXPOSE $PORT

WORKDIR /app

# add a non-privileged user for installing and running the application
RUN groupadd --gid $groupid app && \
    useradd -g app --uid $userid --shell /usr/sbin/nologin --create-home app && \
    chown app:app /app/

# install a few essentials and clean apt caches afterwards
RUN apt-get update && \
    apt-get install -y --no-install-recommends apt-transport-https build-essential curl git libpq-dev gettext libffi-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python dependencies
COPY requirements.txt /tmp/

# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp

# 23.5 is incompatible with pip-tools < 7.5.3 due to
# https://github.com/jazzband/pip-tools/issues/2252, and we can't upgrade
# pip-tools due to this regression: https://github.com/jazzband/pip-tools/issues/2220.
RUN pip install -U 'pip>=20,<23.5' && \
    pip install --no-cache-dir --no-deps -r requirements.txt && \
    pip check --disable-pip-version-check

COPY . /app

# Switch back to home directory
WORKDIR /app

RUN chown -R app:app /app

USER app

ENTRYPOINT ["/bin/bash", "/app/bin/entrypoint.sh"]

CMD ["eliot"]
