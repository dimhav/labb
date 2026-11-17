# ===========================================================================
#  Superset - byggs ovanpa den officiella imagen.
#  Bas-image styrs av build-arg SUPERSET_IMAGE (fran .env).
# ===========================================================================
ARG SUPERSET_IMAGE=apache/superset:5.0.0
FROM ${SUPERSET_IMAGE}

# Bevara kallversionen sa att version-manager kan lasa den korande versionen
# (image-taggen pgsqlmesh/superset innehaller ingen version).
ARG SUPERSET_IMAGE
LABEL org.pgsqlmesh.source-image="${SUPERSET_IMAGE}"

USER root

# psycopg2 behovs for Postgres-metadata (saknas i "lean"-imagen).
RUN uv pip install --python /app/.venv/bin/python psycopg2-binary

COPY superset_config.py /app/pythonpath/superset_config.py
COPY setup_assets.py /app/pgsqlmesh-setup-assets.py
COPY bootstrap.sh /app/pgsqlmesh-bootstrap.sh
RUN chmod 0644 /app/pythonpath/superset_config.py /app/pgsqlmesh-setup-assets.py \
    && chmod 0755 /app/pgsqlmesh-bootstrap.sh

USER superset

CMD ["/app/pgsqlmesh-bootstrap.sh"]
