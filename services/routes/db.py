# services/routes/db.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.db_service import check_connection, save_connection
from core.db_service import list_db_connections, get_db_connection, update_db_connection

router = APIRouter(tags=["db"])


class CheckReq(BaseModel):
    host: str
    port: str
    user: str
    password: str
    database: str


class SaveReq(BaseModel):
    conn_name: str
    host: str
    port: str
    user: str
    password: str
    database: str
    db_type: str


class UpdateVTReq(BaseModel):
    no: int
    conn_name: str
    database: str
    host: str
    port: str
    user: str
    password: str
    db_type: str


@router.post("/check")
def db_check(req: CheckReq):
    return check_connection(
        host=req.host,
        port=req.port,
        user=req.user,
        password=req.password,
        database=req.database,
    )


@router.post("/save")
def db_save(req: SaveReq):
    if not req.conn_name.strip():
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    return save_connection(
        conn_name=req.conn_name,
        host=req.host,
        port=req.port,
        user=req.user,
        password=req.password,
        database=req.database,
        db_type=req.db_type,
    )


@router.get("/list")
def db_list():
    return list_db_connections()


@router.get("/get/{no}")
def db_get(no: int):
    return get_db_connection(no)


@router.post("/update")
def db_update(req: UpdateVTReq):
    return update_db_connection(
        no=req.no,
        conn_name=req.conn_name,
        database=req.database,
        host=req.host,
        port=req.port,
        user=req.user,
        password=req.password,
        db_type=req.db_type,
    )
