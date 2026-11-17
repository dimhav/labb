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
mallen. For att skicka projektet till en annan OpenHands-anvandare:

```bash
git archive --format=tar.gz --prefix=pgsqlmesh/ -o pgsqlmesh.tar.gz HEAD   # kod, utan .env
git bundle create pgsqlmesh.bundle --all                                  # med git-historik
```

Mottagaren (i OpenHands): ladda upp/klona, kor `cp .env.example .env` och
`docker compose up -d --build`. Ett `git bundle` kan klonas direkt:
`git clone pgsqlmesh.bundle pgsqlmesh`.

For att publicera i ett Git-repo: lagg till en remote och pusha. Pusha aldrig
`.env` - den ar redan ignorerad, men kontrollera `git status` fore push.

## Uppdateringsflodet

`version-manager/app/upgrader.py` skriver ny version till `.env`, bygger om vid
behov, kor `up -d --no-deps --pull always <tjanst>`, vantar in healthcheck och
**verifierar att korande version faktiskt bytte**. Misslyckas nagot rullas `.env`
tillbaka. Läs korande version via `docker inspect` (image-tagg, eller label
`org.pgsqlmesh.source-image` for lokalt byggda images som Superset).
