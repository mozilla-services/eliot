# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

_default:
    @just --list

_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
      echo "Copying docker/config/env-dist to .env..."
      cp docker/config/env-dist .env
    fi

# Build docker images.
build *args='base fakesentry statsd': _env
    docker compose --progress plain build {{args}}

# Run the webapp and services.
run *args='--attach=eliot --attach=fakesentry eliot': _env
    docker compose up {{args}}

# Stop service containers.
stop *args:
    docker compose stop {{args}}

# Remove service containers and networks.
down *args:
    docker compose down {{args}}

# Open a shell in the web image.
shell *args='/bin/bash': _env
    docker compose run --rm --entrypoint= eliot {{args}}

# Open a shell in the test container.
test-shell *args='/bin/bash': _env
    docker compose run --rm --entrypoint= test {{args}}

# Stop and remove docker containers and artifacts.
clean:
    docker compose down

# Run tests.
test *args: _env
    docker compose run --rm test bash ./bin/run_test.sh {{args}}

# Generate Sphinx HTML documentation.
docs: _env
    docker compose run --rm --no-deps eliot bash make -C docs/ clean
    docker compose run --rm --no-deps eliot bash make -C docs/ html

# Lint code, or use --fix to reformat and apply auto-fixes for lint.
lint *args: _env
    docker compose run --rm --no-deps eliot bash ./bin/run_lint.sh {{args}}

# Run uv inside the container
uv *args: _env
	docker compose run --rm --no-deps eliot bash uv {{args}}

# Check how far behind different server environments are from main tip.
service-status *args:
    docker compose run --rm --no-deps eliot bash service-status {{args}}
