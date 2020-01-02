FROM node:10.18.0-slim@sha256:7da09bec069149d866c112c6dffe6b5ef51e1bcc45afb88650e47055fef53c3f as frontend

# these build args are turned into env vars
# and used in bin/build_frontend.sh
ARG FRONTEND_SENTRY_PUBLIC_DSN=UNSET_DSN
ENV FRONTEND_SENTRY_PUBLIC_DSN=${FRONTEND_SENTRY_PUBLIC_DSN}
ARG CI=false
ENV CI=${CI}

RUN echo "Running in CI: ${CI}"

COPY . /app
WORKDIR /app
RUN bin/build_frontend.sh

# NOTE(willkg): stick with stretch because it has gcc-6 which we need
# to build dump_syms.
FROM python:3.7.6-slim-stretch@sha256:8e9602a414be1aa0bc1df1d6227021a8cc33ac2b6f8d02112dca24b4400d0d24

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/ \
    DJANGO_CONFIGURATION=Prod \
    PORT=8000

EXPOSE $PORT

# add a non-privileged user for installing and running the application
# don't use --create-home option to prevent populating with skeleton files
RUN mkdir /app && \
    chown 10001:10001 /app && \
    groupadd --gid 10001 app && \
    useradd --no-create-home --uid 10001 --gid 10001 --home-dir /app app

# install a few essentials and clean apt caches afterwards
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https build-essential curl git libpq-dev \
    gettext libffi-dev jed

# Install dump_syms
RUN DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    gyp ninja-build binutils-gold gcc-6 g++-6 pkg-config cabextract
COPY ./docker/build_dump_syms.sh /tmp
RUN /tmp/build_dump_syms.sh

# Clean up apt
RUN apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python dependencies
COPY ./requirements /tmp/requirements
# Switch to /tmp to install dependencies outside home dir
WORKDIR /tmp
RUN pip install -U 'pip>=10' && \
    pip install --no-cache-dir -r requirements/default.txt && \
    pip check --disable-pip-version-check

COPY . /app

# Switch back to home directory
WORKDIR /app

# Copy static assets
COPY --from=frontend /app/frontend/build /app/frontend/build

RUN chown -R 10001:10001 /app

USER 10001

# Using /bin/bash as the entrypoint works around some volume mount issues on Windows
# where volume-mounted files do not have execute bits set.
# https://github.com/docker/compose/issues/2301#issuecomment-154450785 has additional background.
ENTRYPOINT ["/bin/bash", "/app/bin/run.sh"]

CMD ["web"]