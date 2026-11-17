# ===========================================================================
#  Version Manager
#  - Kontrollerar komponentversioner mot Docker Hub / PyPI
#  - Kontrollerar sakerhetsrisker (CVE) mot OSV.dev och NVD
#  - Kan utfora uppdateringarna via docker compose
#
#  docker-CLI + compose-pluginen kopieras fran den officiella docker-imagen
#  sa att tjansten kan bygga och starta om de andra tjansterna.
# ===========================================================================
FROM docker:29-cli AS dockercli

FROM python:3.11-slim

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
RUN chmod -R a+rX /srv

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
