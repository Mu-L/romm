# Stages:
#   - frontend-build: Build frontend
#   - backend-build: Build backend environment
#   - backend-dev-build: Similar to `backend-build`, but also compiles and installs development dependencies
#   - rahasher-build: Build RAHasher
#   - emulator-stage: Fetch and extract emulators
#   - nginx-build: Build nginx modules
#   - production-stage: Setup frontend and backend
#   - slim-image: Slim image with only the necessary files
#   - full-image: Full image with emulator stage
#   - dev-slim: Slim image with development dependencies
#   - dev-full: Full image with emulator stage and development dependencies

# Versions:
ARG ALPINE_VERSION=3.22
ARG NGINX_VERSION=1.29.0
ARG NODE_VERSION=20.19
ARG PYTHON_VERSION=3.13

# Alias stages:
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS python-alias


FROM node:${NODE_VERSION}-alpine${ALPINE_VERSION} AS frontend-build
WORKDIR /front

COPY ./frontend/package*.json ./
RUN npm ci

COPY ./frontend ./
RUN npm run build


FROM python-alias AS backend-build

# git is needed to install streaming-form-data fork
# linux-headers is needed to install py7zr
# libpq-dev is needed to build psycopg-c
# mariadb-connector-c-dev is needed to build mariadb-connector
RUN apk add --no-cache \
    gcc \
    git \
    linux-headers \
    libpq-dev \
    mariadb-connector-c-dev \
    musl-dev

COPY --from=ghcr.io/astral-sh/uv:0.7.19 /uv /uvx /bin/

WORKDIR /src

COPY ./pyproject.toml ./uv.lock /src/
RUN uv sync --locked --no-cache


FROM backend-build AS backend-dev-build

RUN uv sync --locked --no-cache --all-extras


FROM alpine:${ALPINE_VERSION} AS rahasher-build

RUN apk add --no-cache \
    g++ \
    git \
    linux-headers \
    make \
    zlib-dev

ARG RALIBRETRO_VERSION=1.8.1

# TODO: Remove `sed` command adding "ctime", when RAHasher can be compiled without it.
# TODO: Remove `sed` command adding "unistd.h", when RAHasher can be compiled without it.
#       Related pull request: https://github.com/madler/zlib/pull/1022
RUN git clone --recursive --branch "${RALIBRETRO_VERSION}" --depth 1 https://github.com/RetroAchievements/RALibretro.git && \
    cd ./RALibretro && \
    sed -i '22a #include <ctime>' ./src/Util.h && \
    sed -i '6a #include <unistd.h>' \
      ./src/libchdr/deps/zlib-1.3.1/gzlib.c \
      ./src/libchdr/deps/zlib-1.3.1/gzread.c \
      ./src/libchdr/deps/zlib-1.3.1/gzwrite.c && \
    make HAVE_CHD=1 -f ./Makefile.RAHasher


FROM alpine:${ALPINE_VERSION} AS emulator-stage

RUN apk add --no-cache \
    7zip \
    wget

ARG EMULATORJS_VERSION=4.2.3
RUN wget "https://github.com/EmulatorJS/EmulatorJS/releases/download/v${EMULATORJS_VERSION}/${EMULATORJS_VERSION}.7z" && \
    7z x -y "${EMULATORJS_VERSION}.7z" -o/emulatorjs && \
    rm -rf "${EMULATORJS_VERSION}.7z";

ARG RUFFLE_VERSION=nightly-2024-12-28
ARG RUFFLE_FILE=ruffle-nightly-2024_12_28-web-selfhosted.zip
RUN wget "https://github.com/ruffle-rs/ruffle/releases/download/${RUFFLE_VERSION}/${RUFFLE_FILE}" && \
    unzip -o "${RUFFLE_FILE}" -d /ruffle && \
    rm -f "${RUFFLE_FILE}";

FROM alpine:${ALPINE_VERSION} AS nginx-build

RUN apk add --no-cache \
    gcc \
    git \
    libc-dev \
    make \
    pcre-dev \
    zlib-dev

ARG NGINX_VERSION
# The specified commit SHA is the latest commit on the `master` branch at the time of writing.
# It includes a fix to correctly calculate CRC-32 checksums when using upstream subrequests.
# TODO: Move to a tagged release of `mod_zip`, once a version newer than 1.3.0 is released.
ARG NGINX_MOD_ZIP_SHA=8e65b82c82c7890f67a6107271c127e9881b6313

# Clone both nginx and `ngx_http_zip_module` repositories, needed to compile the module from source.
# This is needed to be able to dinamically load it as a module in the final image. `nginx` Docker
# images do not have a simple way to include third-party modules.
RUN git clone https://github.com/evanmiller/mod_zip.git && \
    cd ./mod_zip && \
    git checkout "${NGINX_MOD_ZIP_SHA}" && \
    cd ../ && \
    git clone --branch "release-${NGINX_VERSION}" --depth 1 https://github.com/nginx/nginx.git && \
    cd ./nginx && \
    ./auto/configure --with-compat --add-dynamic-module=../mod_zip/ && \
    make -f ./objs/Makefile modules && \
    chmod 644 ./objs/ngx_http_zip_module.so


FROM nginx:${NGINX_VERSION}-alpine${ALPINE_VERSION} AS production-stage
ARG WEBSERVER_FOLDER=/var/www/html

# Install required packages and dependencies
RUN apk add --no-cache \
    bash \
    libmagic \
    mariadb-connector-c \
    libpq \
    p7zip \
    tzdata \
    valkey

# Add Python by copying it from the official Docker image. This way, we don't rely on Alpine's
# Python version, which could not be the same as the one used in the backend build stage.
# TODO: Replace with a bundled installation of Python using `uv`, when it is supported.
#       Related issue: https://github.com/astral-sh/uv/issues/7865
ARG PYTHON_VERSION
COPY --from=python-alias /usr/lib/* /usr/lib/
COPY --from=python-alias /usr/local/bin/* /usr/local/bin/
COPY --from=python-alias /usr/local/include/python${PYTHON_VERSION} /usr/local/include/python${PYTHON_VERSION}
COPY --from=python-alias /usr/local/lib/libpython* /usr/local/lib/
COPY --from=python-alias /usr/local/lib/python${PYTHON_VERSION} /usr/local/lib/python${PYTHON_VERSION}

COPY --from=rahasher-build /RALibretro/bin64/RAHasher /usr/bin/RAHasher
COPY --from=nginx-build ./nginx/objs/ngx_http_zip_module.so /usr/lib/nginx/modules/
COPY --from=frontend-build /front/dist ${WEBSERVER_FOLDER}

COPY ./frontend/assets ${WEBSERVER_FOLDER}/assets
RUN mkdir -p ${WEBSERVER_FOLDER}/assets/romm && \
    ln -sf /romm/resources ${WEBSERVER_FOLDER}/assets/romm/resources && \
    ln -sf /romm/assets ${WEBSERVER_FOLDER}/assets/romm/assets
COPY ./backend /backend

# Setup init script and config files
COPY ./docker/init_scripts/* /
COPY ./docker/nginx/js/ /etc/nginx/js/
COPY ./docker/nginx/templates/ /etc/nginx/templates/
COPY ./docker/nginx/default.conf /etc/nginx/nginx.conf
COPY ./docker/gunicorn/logging.conf /etc/gunicorn/logging.conf

# User permissions
# - Create default user `romm` (1000) and group `romm` (1000).
# - Create base directories and make default user/group the owner.
# - Make nginx configuration files writable by everyone, for `envsubst` to work
#     when a custom UID/GID is used.
RUN addgroup -g 1000 -S romm && adduser -u 1000 -D -S -G romm romm && \
    mkdir /romm /redis-data && chown romm:romm /romm /redis-data && \
    chmod -R a+w /etc/nginx/conf.d


FROM scratch AS slim-image

COPY --from=production-stage / /

COPY --from=backend-build /src/.venv /src/.venv

ENV PATH="/src/.venv/bin:${PATH}"

# Declare the supported volumes
VOLUME ["/romm/resources", "/romm/library", "/romm/assets", "/romm/config", "/redis-data"]

# Expose ports and start
EXPOSE 8080 6379/tcp
WORKDIR /romm

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/init"]


FROM slim-image AS full-image
ARG WEBSERVER_FOLDER=/var/www/html
COPY --from=emulator-stage /emulatorjs ${WEBSERVER_FOLDER}/assets/emulatorjs
COPY --from=emulator-stage /ruffle ${WEBSERVER_FOLDER}/assets/ruffle


FROM slim-image AS dev-slim
COPY --from=backend-dev-build /src/.venv /src/.venv


FROM full-image AS dev-full
COPY --from=backend-dev-build /src/.venv /src/.venv
