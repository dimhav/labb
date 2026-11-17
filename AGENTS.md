# pgsqlmesh - agentanteckningar

Dataplattform: Postgres -> SQLMesh -> Superset, plus en version-manager-portal
(FastAPI + vanilla JS) pa port 12000. Allt kor via Docker Compose.

## Viktigt: `.env` ar enda kallan for versioner

`docker compose` laser `POSTGRES_IMAGE`, `SQLMESH_VERSION` och `SUPERSET_IMAGE`
fran `.env` - men en **miljovariabel i skalet vinner over `.env`**. Om skalet
har en gammal variabel (t.ex. `POSTGRES_IMAGE=postgres:17.12` kvar fran en
tidigare uppdatering) startar containern med den versionen aven om `.env`
anger nagot annat, och portalen visar en falsk avvikelse.

Kontrollera alltid fore start/uppdatering:

```bash
env | grep -E '^(POSTGRES_IMAGE|SQLMESH_VERSION|SUPERSET_IMAGE)='
unset POSTGRES_IMAGE SQLMESH_VERSION SUPERSET_IMAGE   # om nagot ligger kvar
```

## Docker-daemonen

Startas med `sudo dockerd > /tmp/docker.log 2>&1 &`. Socketen kan behova
`sudo chmod 666 /var/run/docker.sock`. Daemonen ar **inte persistent** - efter
en omstart ar volymer/images borta och stacken maste byggas fran scratch med
`docker compose up -d --build`.

## Nedgradering (for att kunna testa uppdateringen igen)

Att ga tillbaka fran t.ex. Superset 6.1.0 till 5.0.0 ar inte en framat-migrering,
sa metadata maste aterskapas. Steg:

1. `unset` skalvariablerna ovan; sat `.env` till baslinjen
   (postgres 17.6, sqlmesh 0.227.0, superset 5.0.0).
2. `docker compose stop sqlmesh superset`.
3. Aterskapa metadata/tillstand (raw-data behalls):
   ```sql
   DROP DATABASE IF EXISTS superset; CREATE DATABASE superset OWNER superset;
   DROP SCHEMA IF EXISTS sqlmesh CASCADE;
   DROP SCHEMA IF EXISTS sqlmesh__analytics CASCADE;
   DROP SCHEMA IF EXISTS analytics CASCADE;
   ```
4. `docker compose build sqlmesh superset && docker compose up -d sqlmesh superset`.
   Supersets bootstrap kor `superset db upgrade` + skapar dataset/dashboard;
   SQLMesh:s entrypoint bygger om `analytics.*` fran `raw.*`.

## Dela / overlamna projektet

`.env` ar gitignorerad (innehaller losenord + secret key). `.env.example` ar
mallen, och `./start.sh` skapar `.env` automatiskt vid forsta korningen.

Tva paket skapas i `/workspace` (utanfor projektet, sa de inte hamnar i repot):

```bash
# zip med .git - packas upp, redan ett repo, kor start.sh
cd /tmp && cp -a project pgsqlmesh && (cd pgsqlmesh && rm -f .env)
zip -r -y /workspace/pgsqlmesh-repo.zip pgsqlmesh

# bundle - en fil som klonas direkt, behaller historiken
git bundle create /workspace/pgsqlmesh.bundle --all
```

Mottagaren (i OpenHands):

```bash
# alternativ 1: zip
unzip pgsqlmesh-repo.zip && cd pgsqlmesh && ./start.sh

# alternativ 2: bundle
git clone pgsqlmesh.bundle pgsqlmesh && cd pgsqlmesh && ./start.sh
```

`./start.sh` skapar `.env`, rensar skalvariabler som overskuggar `.env`, och
kor `docker compose up -d --build`. For att publicera i ett Git-repo: lagg till
en remote och pusha. Pusha aldrig `.env`.

Paketen laggs aven i arbetsytans rot (`/workspace/project/`) sa de gar att ladda
ner direkt i OpenHands UI (filbladdraren/VS Code). De ar gitignorerade (`*.zip`,
`*.bundle`) sa de hamnar inte i repot. Verifiera alltid med `unzip -q` - Python-
uppackning tappar korbarhetsbiten och ger falska "M"-poster i `git status`.

## Uppdateringsflodet

`version-manager/app/upgrader.py` skriver ny version till `.env`, bygger om vid
behov, kor `up -d --no-deps --pull always <tjanst>`, vantar in healthcheck och
**verifierar att korande version faktiskt bytte**. Misslyckas nagot rullas `.env`
tillbaka. Läs korande version via `docker inspect` (image-tagg, eller label
`org.pgsqlmesh.source-image` for lokalt byggda images som Superset).
