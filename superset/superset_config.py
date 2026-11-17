# ===========================================================================
#  Superset-konfiguration for pgsqlmesh.
#  Ligger pa PYTHONPATH=/app/pythonpath och laddas automatiskt.
# ===========================================================================
import os

# --- Sakarhet ---------------------------------------------------------------
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# --- Metadata-databas (Postgres) -------------------------------------------
_db = os.environ.get("SUPERSET_DB", "superset")
_user = os.environ.get("SUPERSET_DB_USER", "superset")
_password = os.environ.get("SUPERSET_DB_PASSWORD", "superset")
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{_user}:{_password}@postgres:5432/{_db}"
)

# --- Omgivning --------------------------------------------------------------
ENVIRONMENT = "production"
ENABLE_PROXY_FIX = True

# --- Datalager som skall vara forregistrerat --------------------------------
WAREHOUSE_DB = os.environ.get("WAREHOUSE_DB", "warehouse")
WAREHOUSE_USER = os.environ.get("WAREHOUSE_USER", "warehouse")
WAREHOUSE_PASSWORD = os.environ.get("WAREHOUSE_PASSWORD", "warehouse")
SQLALCHEMY_EXAMPLES_URI = (
    f"postgresql+psycopg2://{WAREHOUSE_USER}:{WAREHOUSE_PASSWORD}"
    f"@postgres:5432/{WAREHOUSE_DB}"
)

# --- Dashboard-standard -----------------------------------------------------
DASHBOARD_AUTO_REFRESH_INTERVALS = [
    [0, "Don't refresh"],
    [30, "30 seconds"],
    [60, "1 minute"],
    [300, "5 minutes"],
]

# --- Feature-flaggor --------------------------------------------------------
FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    "EMBEDDED_SUPERSET": True,
}
