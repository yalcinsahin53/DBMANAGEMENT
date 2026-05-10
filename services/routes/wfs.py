# services/routes/wfs.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from core import wfs_service
from core.wfs_service import download_gml_bytes, download_vector_bytes
import io

# services/routes/wfs.py
from core.wfs_service import download_xsd_bytes  # ✅ ekle

from core.wfs_service import (
    wfs_check_connection,
    wfs_save_connection,
    list_wfs_connections,
    fetch_typenames_for_connection,
)

router = APIRouter(prefix="/api/v1/wfs", tags=["wfs"])


class WFSCheckReq(BaseModel):
    urladress: str
    username: str = ""
    password: str = ""
    timeout: int = 10


class WFSSaveReq(BaseModel):
    conn_name: str
    urladress: str
    username: str = ""
    password: str = ""


@router.post("/check")
def wfs_check(req: WFSCheckReq):
    return wfs_check_connection(
        urladress=req.urladress,
        username=req.username,
        password=req.password,
        timeout=req.timeout,
    )


@router.post("/save")
def wfs_save(req: WFSSaveReq):
    if not (req.conn_name or "").strip():
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not (req.urladress or "").strip():
        raise HTTPException(status_code=400, detail="urladress boş olamaz")

    return wfs_save_connection(
        conn_name=req.conn_name,
        urladress=req.urladress,
        username=req.username,
        password=req.password,
    )


@router.get("/list")
def list_connections():
    return wfs_service.list_wfs_connections()


@router.get("/typenames")
def typenames(conn_name: str = Query(...)):
    return wfs_service.fetch_typenames_for_connection(conn_name)


@router.get("/fields")
def fields(conn_name: str = Query(...), typename: str = Query(...)):
    return wfs_service.fetch_fieldnames(conn_name, typename)


@router.get("/typenames-meta")
def typenames_meta(conn_name: str = Query(...)):
    return wfs_service.fetch_typenames_with_geom(conn_name)


@router.get("/fields-meta")
def fields_meta(conn_name: str = Query(...), typename: str = Query(...)):
    return wfs_service.fetch_fieldinfo(conn_name, typename)


@router.get("/count")
def count(conn_name: str = Query(...), typename: str = Query(...)):
    return wfs_service.count_features(conn_name, typename)


@router.get("/field-values")
def field_values(
    conn_name: str = Query(...),
    typename: str = Query(...),
    field: str = Query(...),
):
    return wfs_service.fetch_field_values_all(conn_name, typename, field)


@router.get("/download-gml")
def wfs_download_gml(conn_name: str, typename: str, cql_filter: str = ""):

    print("ROUTE /download-gml cql_filter =", repr(cql_filter))

    res = download_gml_bytes(
        conn_name=conn_name,
        typename=typename,
        cql_filter=(cql_filter or "").strip() or None,
    )

    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": res.get("message", "GML indirilemedi."),
                "debug": res.get("debug", ""),
                "title": res.get("title", "Hata"),
            },
        )

    data = res.get("data") or {}
    filename = data.get("filename", "wfs_export.gml")
    content: bytes = data.get("bytes") or b""

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/gml+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download-vector")
def wfs_download_vector(
    conn_name: str,
    typename: str,
    vector_format: str = Query("gml"),
    cql_filter: str = "",
):
    fmt = (vector_format or "gml").strip().lower()
    if fmt not in ("gml", "shp"):
        raise HTTPException(status_code=400, detail="vector_format must be gml or shp")

    res = download_vector_bytes(
        conn_name=conn_name,
        typename=typename,
        vector_format=fmt,
        cql_filter=(cql_filter or "").strip() or None,
    )

    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": res.get("message", "Vektör veri indirilemedi."),
                "debug": res.get("debug", ""),
                "title": res.get("title", "Hata"),
            },
        )

    data = res.get("data") or {}
    filename = data.get("filename", "wfs_export.gml")
    content: bytes = data.get("bytes") or b""
    fmt = (data.get("vector_format") or fmt or "gml").lower()
    media_type = "application/zip" if fmt == "shp" else "application/gml+xml"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download-xsd")
def wfs_download_xsd(conn_name: str, typename: str):
    res = download_xsd_bytes(conn_name=conn_name, typename=typename)

    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": res.get("message", "XSD indirilemedi."),
                "debug": res.get("debug", ""),
                "title": res.get("title", "Hata"),
            },
        )

    data = res.get("data") or {}
    filename = data.get("filename", "schema.xsd")
    content: bytes = data.get("bytes") or b""

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
