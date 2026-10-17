# syntax=docker/dockerfile:1
#
# Build targets:
#   offline  - Python 3.12/3.13/3.14 via uv, nox, unixODBC. No IBM software.
#   full     - offline + IBM i Access ODBC Driver for Linux.
#
# The "full" image contains IBM-licensed software. Build it locally or in
# private CI only; NEVER push it to a public registry.
#
# IBM ships the driver for amd64 (plus i386/ppc64el), not arm64: build and run
# the "full" target with --platform linux/amd64 on Apple Silicon.

ARG DEBIAN_TAG=trixie-slim
ARG UV_VERSION=0.13.1

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------------------------------------------------------------------------
FROM debian:${DEBIAN_TAG} AS offline

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git gnupg libodbc2 odbcinst unixodbc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/opt/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/home/dev/.cache/uv \
    PYTHONDONTWRITEBYTECODE=1

ARG NOX_VERSION=2026.8.17
RUN uv python install 3.12 3.13 3.14 \
    && uv tool install "nox==${NOX_VERSION}" \
    && rm -rf /home/dev/.cache/uv

# Non-root user. The directories below are mount points for named volumes;
# creating them here makes the volumes inherit the dev user's ownership.
RUN useradd --create-home --uid 1000 --shell /bin/bash dev \
    && mkdir -p /workspace/.nox /home/dev/.cache/uv \
    && chown -R dev:dev /workspace /home/dev

USER dev
WORKDIR /workspace
CMD ["nox", "--list"]

# ---------------------------------------------------------------------------
FROM offline AS full

USER root

# IBM's apt repository is unsigned ([trusted=yes] in IBM's own .list file), so
# the package is pinned by version and verified by SHA256 instead. Checksum
# from dists/1.1.0/main/binary-amd64/Packages.
ARG IACCESS_VERSION=1.1.0.29-1.0
ARG IACCESS_SHA256=e60e968d2cee96b2851964456f5b31ab990b1aa47d8f2399607809f7d4514f58
ARG IACCESS_URL=https://public.dhe.ibm.com/software/ibmi/products/odbc/debs/dists/1.1.0/main/binary-amd64

RUN curl -fsSL -o /tmp/ibm-iaccess.deb "${IACCESS_URL}/ibm-iaccess-${IACCESS_VERSION}.amd64.deb" \
    && echo "${IACCESS_SHA256}  /tmp/ibm-iaccess.deb" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/ibm-iaccess.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/ibm-iaccess.deb

COPY docker/odbcinst.ini /etc/odbcinst.ini

# Fail the build if the driver is not registered or its libraries do not resolve.
RUN odbcinst -q -d -n "IBM i Access ODBC Driver" \
    && test -f /opt/ibm/iaccess/lib64/libcwbodbc.so \
    && ! ldd /opt/ibm/iaccess/lib64/libcwbodbc.so | grep -q "not found"

USER dev
