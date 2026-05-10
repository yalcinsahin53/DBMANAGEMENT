# services/api_server.py
from fastapi import FastAPI

from services.routes.db import router as db_router
from services.routes.wfs import router as wfs_router
from services.routes.createpostgisschema import router as postgis_schema_router
from services.routes.createfeature import router as create_feature_router
from services.routes.createesrifeature import router as create_esri_feature_router
from services.routes.createandeditfield import router as create_and_edit_field_router
from services.routes.createandeditfieldesri import router as create_and_edit_field_esri_router
from services.routes.dbcheckdublicateanddelete import router as db_check_duplicate_delete_router
from services.routes.dbcheckdublicateanddeleteesri import router as db_check_duplicate_delete_esri_router
from services.routes.dbdeletefeature import router as db_delete_feature_router
from services.routes.dbdeletefeatureesri import router as db_delete_feature_esri_router
from services.routes.importfeaturetoesri import router as esri_import_router
from services.routes.createfeaturefromxsdesri import router as create_feature_from_xsd_esri_router
from services.routes.dbmatchfeatureandloadesri import router as db_match_feature_and_load_esri_router

app = FastAPI(title="DBManagement Local API")


@app.get("/health")
def health():
    return {"ok": True}


# Mevcut URL’leri KORUMAK için prefix’i burada veriyoruz:
# UI şu URL’lere çağrı yapıyordu:
# /api/v1/db/check, /api/v1/db/save, /api/v1/db/list, /api/v1/db/get/{no}, /api/v1/db/update
# Bu yüzden db_router'ı aynı prefix’e bağlıyoruz.
# VT (mevcut URL’leri koruyoruz)
app.include_router(db_router, prefix="/api/v1/db")
app.include_router(wfs_router)
app.include_router(postgis_schema_router, prefix="/api/v1/db")
app.include_router(create_feature_router, prefix="/api/v1/db")
app.include_router(create_esri_feature_router, prefix="/api/v1/db")
app.include_router(create_and_edit_field_router, prefix="/api/v1/db")
app.include_router(create_and_edit_field_esri_router, prefix="/api/v1/db")
app.include_router(db_check_duplicate_delete_router, prefix="/api/v1/db")
app.include_router(db_check_duplicate_delete_esri_router, prefix="/api/v1/db")
app.include_router(db_delete_feature_router, prefix="/api/v1/db")
app.include_router(db_delete_feature_esri_router, prefix="/api/v1/db")
app.include_router(esri_import_router, prefix="/api/v1/db")
app.include_router(create_feature_from_xsd_esri_router, prefix="/api/v1/db")
app.include_router(db_match_feature_and_load_esri_router, prefix="/api/v1/db")
