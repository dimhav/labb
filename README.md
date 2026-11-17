# pgsqlmesh

En liten dataplattform byggd av tre applikationer som hanger ihop, plus en
fjarde tjanst som kontrollerar och uppdaterar de andras versioner.

```
Postgres  ->  SQLMesh  ->  Superset
(datalager)   (transform)   (BI)
```

| Tjanst | Roll | Port |
| --- | --- | --- |
| PostgreSQL | Datalager: `raw.*` (radata) och `analytics.*` (modeller). Ar ocksa Supersets metadata-databas. | 5432 (endast localhost) |
| SQLMesh | Transformationslager: laser `raw.*` och bygger `analytics.*`. | - |
| Apache Superset | BI-lager: dashboards och utforskning av `analytics.*`. | 12001 |
| pgsqlmesh portal | Webbapp som visar hela plattformen och hanterar versioner + sakerhet. | 12000 |

## Webbappen

Allt samlas i en webbapp pa port 12000 med fyra flikar:

* **Översikt** - tjansternas driftstatus, versioner och nyckeltal for datalagret.
* **Versioner & säkerhet** - knappen som kontrollerar versioner, skannar efter
  CVE:er, visar åtgärdsförslag och kan utföra uppdateringarna.
* **Data** - alla tabeller i `raw.*` och `analytics.*` med radantal; klicka for
  att se innehallet.
* **Superset** - lank och inloggning till BI-lagret.

### Grafisk profil

Gränssnittet följer Havs- och vattenmyndighetens grafiska profil:

* **Färgpalett** - profilens HEX-värden används direkt (`--hav-*` i `style.css`),
  med turkos/blå som bas och orange/gul som signalfärger.
* **Typografi** - TT Norms primärt, med Arial som fallback.
* **Mönster och element** - diskreta vattenmotiv i bakgrunden och i logotypen.
* **Tillgänglighet** - färg är aldrig enda ledtråden; allvarlighetsgrader visas
  med både symbol, text och färg, och kontrasterna håller WCAG AA (>= 4.5:1).

## Kom igang

```bash
docker compose up -d --build
```

Tjansterna startar i ordning: Postgres seedar radata, SQLMesh bygger
modellerna, Superset skapar dataset och en dashboard.

* Webbapp (portal): <http://localhost:12000>
* Superset: <http://localhost:12001> (admin / admin)

### Fjarrakomst (utan lokal installation)

Kor stacken i en fjarrserver sa nas webbappen via en publik adress i stallet:

* Portal: <https://work-1-abcgbfugcnpbijmn.prod-runtime.all-hands.dev/>
* Superset: <https://work-2-abcgbfugcnpbijmn.prod-runtime.all-hands.dev/>

Inget behover installeras lokalt - allt kor i containrar pa servern.

## Versioner

Alla versioner styrs fran `.env` - en enda kalla. Utgangslaget ar medvetet
ca ett ar gammalt for att det skall finnas nagot att uppdatera:

```
POSTGRES_IMAGE=postgres:17.6
SQLMESH_VERSION=0.227.0
SUPERSET_IMAGE=apache/superset:5.0.0
```

Portalen skiljer på **deklarerad** version (`.env`) och **körande** version
(den som faktiskt svarar i containern). Om de inte stämmer visas en
avvikelsevarning på komponentkortet, så att en misslyckad uppdatering inte
kan se ut som en lyckad.

## Version Manager

Knappen **Kontrollera versioner** i webbgranssnittet (eller `POST /api/check`)
gor foljande for varje komponent:

1. Slar upp senaste tillgangliga version (Docker Hub / PyPI).
2. Skannar nuvarande version efter kanda sarbarheter (NVD och OSV).
3. Visar tydliga atgardsforslag: vilken version som rekommenderas, hur manga
   fynd den ratar och vad som kvarstar efterat.
4. Knappen **Uppdatera** utfor sjalva uppdateringen: skriver ny version till
   `.env`, bygger om vid behov, startar om tjansten, vantar in healthcheck och
   **verifierar att den korande versionen faktiskt bytte**. Misslyckas
   uppdateringen rullas `.env` tillbaka och felet rapporteras - ingen falsk
   "uppdaterad"-status.

Resultatet strommas ut komponent for komponent (Server-Sent Events), sa att
granssnittet visar nagot medan skanningen pagar.

### API

| Metod | Vag | Beskrivning |
| --- | --- | --- |
| `POST` | `/api/check` | Kontroll av alla komponenter (SSE). |
| `POST` | `/api/upgrade` | Utfor uppdatering. Body: `{"key": "...", "target": "..."}` (SSE). |
| `GET` | `/api/overview` | Tjanster, versioner och datalagerstatistik. |
| `GET` | `/api/data/tables` | Tabeller i `raw.*` och `analytics.*`. |
| `GET` | `/api/data/{schema}/{table}` | Forsta raderna i en tabell. |
| `GET` | `/api/status` | Driftstatus for tjansterna. |
| `GET` | `/api/health` | Enkel halsa for tjansten sjalv. |

## Struktur

```
docker-compose.yml        hela stacken
.env                      versioner + credentials (single source of truth)
db/init/                  skapar databaser och seedar raw.*
sqlmesh/                  modeller (staging -> marts) + entrypoint
superset/                 config, bootstrap och dashboard-setup
version-manager/          backend (FastAPI) + frontend (vanilla JS)
```

## Noter

* Uppdateringar ar komponentvisa. Postgres-data ligger kvar i volymen
  `pgdata` och overlever en minor-uppdatering.
* Superset kor `superset db upgrade` automatiskt vid start.
* SQLMesh kor `sqlmesh migrate` automatiskt om tillstandstabellerna behover
  migreras efter ett versionsbyte.
* NVD:s API ar rate-limiterat; skanningen tar darfor en stund forsta gangen.
  Resultatet cachas i 15 minuter.
