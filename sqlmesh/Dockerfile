# ===========================================================================
#  SQLMesh - transformationslager.
#  Byggs fran python:3.11-slim. Versionen styrs av build-arg SQLMESH_VERSION.
# ===========================================================================
ARG SQLMESH_VERSION=0.227.0
FROM python:3.11-slim

ARG SQLMESH_VERSION
ENV SQLMESH_VERSION=${SQLMESH_VERSION} \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client tini \
    && rm -rf /var/lib/apt/lists/*

# psycopg2-binary ger psycopg2-modulen utan att kompilera (sqlmesh[postgres]
# drar in psycopg2 fran kallkod och kraver pg_config).
RUN pip install "sqlmesh==${SQLMESH_VERSION}" psycopg2-binary

WORKDIR /app
COPY config.yaml entrypoint.sh ./
COPY models ./models
RUN chmod 0644 config.yaml \
    && chmod -R a+rX models \
    && chmod 0755 entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "./entrypoint.sh"]
