FROM python:3.11.7-slim-bullseye@sha256:18faee15e9f6e5eaa7a4098e093a8513275a5075cfeae59091fae641cc703d1a

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

RUN pip install -U 'pip>=20' && \
    pip install --no-cache-dir --no-deps -r requirements.txt && \
    pip check --disable-pip-version-check

COPY . /app

# Switch back to home directory
WORKDIR /app

RUN chown -R app:app /app

USER app

ENTRYPOINT ["/bin/bash", "/app/bin/entrypoint.sh"]

CMD ["eliot"]
