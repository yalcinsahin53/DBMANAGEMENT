from __future__ import annotations

import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class FeatureRecord:
    row_id: int
    feature_type: str
    values: dict[str, str]
    remove_parent: ET.Element | None = None
    remove_element: ET.Element | None = None
    source_index: int | None = None


@dataclass
class VectorDocument:
    path: str
    kind: str  # "gml" | "shp"
    features: list[FeatureRecord]
    fields: list[str]
    tree: ET.ElementTree | None = None
    namespaces: dict[str, str] = field(default_factory=dict)


def _result(ok: bool, message: str, debug: str = "", data=None) -> dict:
    return {"ok": ok, "message": message, "debug": debug, "data": data}


def _local_name(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _iter_nodes_with_parent(root: ET.Element):
    stack: list[tuple[ET.Element | None, ET.Element]] = [(None, root)]
    while stack:
        parent, node = stack.pop()
        yield parent, node
        children = list(node)
        for child in reversed(children):
            stack.append((node, child))


def _collect_namespaces(path: str) -> dict[str, str]:
    namespaces: dict[str, str] = {}
    for event, node in ET.iterparse(path, events=("start-ns",)):
        del event
        prefix, uri = node
        key = prefix or ""
        if key not in namespaces:
            namespaces[key] = uri
    return namespaces


def _feature_values_from_xml(feature_element: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in list(feature_element):
        if not isinstance(child.tag, str):
            continue
        # Geometry/complex alanları dışarıda bırakıp basit alanları kullanıyoruz.
        if len(list(child)) > 0:
            continue
        field_name = _local_name(child.tag)
        text = (child.text or "").strip()
        prev = values.get(field_name, "")
        if not prev:
            values[field_name] = text
        elif text and text not in prev:
            values[field_name] = f"{prev} | {text}"
    return values


def _extract_gml_feature_records(root: ET.Element) -> list[FeatureRecord]:
    records: list[FeatureRecord] = []
    row_id = 1
    wrapper_names = {"member", "featuremember"}

    for parent, container in _iter_nodes_with_parent(root):
        cname = _local_name(container.tag).lower()
        if cname not in ("featuremember", "featuremembers", "member"):
            continue

        if cname in wrapper_names:
            features = [f for f in list(container) if isinstance(f.tag, str)]
            for feature in features:
                remove_parent = container
                remove_element = feature

                # Wrapper altında tek feature varsa wrapper'ı komple sil,
                # böylece boş wfs:member / gml:featureMember kalmasın.
                if parent is not None and len(features) == 1:
                    remove_parent = parent
                    remove_element = container

                records.append(
                    FeatureRecord(
                        row_id=row_id,
                        feature_type=_local_name(feature.tag),
                        values=_feature_values_from_xml(feature),
                        remove_parent=remove_parent,
                        remove_element=remove_element,
                    )
                )
                row_id += 1
            continue

        # gml:featureMembers durumunda direkt child feature'ları al.
        # Eğer child wrapper ise burada atlıyoruz; wrapper kendi turunda işlenir.
        for feature in list(container):
            if not isinstance(feature.tag, str):
                continue
            fname = _local_name(feature.tag).lower()
            if fname in wrapper_names:
                continue

            records.append(
                FeatureRecord(
                    row_id=row_id,
                    feature_type=_local_name(feature.tag),
                    values=_feature_values_from_xml(feature),
                    remove_parent=container,
                    remove_element=feature,
                )
            )
            row_id += 1

    return records


def _load_gml(path: str) -> dict:
    try:
        namespaces = _collect_namespaces(path)
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)

        tree = ET.parse(path)
        root = tree.getroot()
        features = _extract_gml_feature_records(root)
        if not features:
            return _result(
                False,
                "Dosyada analiz edilebilir feature kaydı bulunamadı.",
                "featureMember/featureMembers/member bulunamadı veya boş.",
            )

        field_set: set[str] = set()
        for rec in features:
            field_set.update(rec.values.keys())
        fields = sorted(field_set, key=lambda s: s.lower())
        if not fields:
            return _result(
                False,
                "Dosyada analiz edilebilir alan bulunamadı.",
                "Leaf text alan bulunamadı.",
            )

        return _result(
            True,
            "",
            data=VectorDocument(
                path=path,
                kind="gml",
                tree=tree,
                namespaces=namespaces,
                features=features,
                fields=fields,
            ),
        )
    except Exception as e:
        return _result(False, "GML dosyası okunamadı.", str(e))


def _load_shp(path: str) -> dict:
    try:
        import shapefile  # pyshp
    except Exception as e:
        return _result(
            False,
            "SHP desteği için 'pyshp' modülü gerekli.",
            f"{e}\nKurulum: pip install pyshp",
        )

    try:
        reader = shapefile.Reader(path)
        field_names = [f[0] for f in reader.fields[1:]]  # DeletionFlag hariç
        if not field_names:
            if hasattr(reader, "close"):
                reader.close()
            return _result(False, "SHP içinde alan bulunamadı.", "")

        shape_type_name = getattr(reader, "shapeTypeName", "") or str(
            getattr(reader, "shapeType", "")
        )

        features: list[FeatureRecord] = []
        try:
            iterator = reader.iterShapeRecords()
        except Exception:
            iterator = []

        for idx, sr in enumerate(iterator):
            values: dict[str, str] = {}
            rec_values = list(sr.record)
            for fname, val in zip(field_names, rec_values):
                values[fname] = "" if val is None else str(val).strip()

            features.append(
                FeatureRecord(
                    row_id=idx + 1,
                    feature_type=shape_type_name,
                    values=values,
                    source_index=idx,
                )
            )

        if hasattr(reader, "close"):
            reader.close()

        if not features:
            return _result(False, "SHP içinde analiz edilebilir kayıt bulunamadı.", "")

        return _result(
            True,
            "",
            data=VectorDocument(
                path=path,
                kind="shp",
                features=features,
                fields=field_names,
            ),
        )
    except Exception as e:
        return _result(False, "SHP dosyası okunamadı.", str(e))


def load_vector(path: str) -> dict:
    path = (path or "").strip()
    if not path:
        return _result(False, "Dosya yolu boş olamaz.")
    if not os.path.isfile(path):
        return _result(False, "Dosya bulunamadı.", path)

    ext = os.path.splitext(path)[1].lower()
    if ext in (".gml", ".xml"):
        return _load_gml(path)
    if ext == ".shp":
        return _load_shp(path)
    return _result(False, "Desteklenmeyen dosya türü.", f"Uzantı: {ext}")


# Geriye dönük uyumluluk
def load_gml(path: str) -> dict:
    return load_vector(path)


def analyze_duplicates(doc: VectorDocument, field_name: str) -> dict:
    field_name = (field_name or "").strip()
    if not field_name:
        return _result(False, "Alan adı boş olamaz.")

    pairs: list[tuple[FeatureRecord, str]] = []
    for rec in doc.features:
        value = (rec.values.get(field_name) or "").strip()
        if value:
            pairs.append((rec, value))

    counts = Counter(value for _, value in pairs)
    rows: list[dict] = []
    for rec, value in pairs:
        if counts[value] > 1:
            rows.append(
                {
                    "record_id": rec.row_id,
                    "feature_type": rec.feature_type,
                    "value": value,
                    "group_count": counts[value],
                    "all_values": dict(rec.values),
                }
            )

    rows.sort(key=lambda r: (str(r["value"]).lower(), int(r["record_id"])))
    duplicate_groups = sum(1 for c in counts.values() if c > 1)

    return _result(
        True,
        "",
        data={
            "rows": rows,
            "duplicate_row_count": len(rows),
            "duplicate_group_count": duplicate_groups,
            "feature_count": len(doc.features),
        },
    )


def _delete_gml_record(doc: VectorDocument, record_id: int) -> dict:
    target = next((r for r in doc.features if r.row_id == int(record_id)), None)
    if target is None:
        return _result(False, "Silinecek kayıt bulunamadı.")
    if doc.tree is None or target.remove_parent is None or target.remove_element is None:
        return _result(False, "GML kayıt yapısı eksik.", "remove_parent/remove_element yok.")

    try:
        backup_path = f"{doc.path}.bak"
        if not os.path.exists(backup_path):
            shutil.copy2(doc.path, backup_path)

        target.remove_parent.remove(target.remove_element)

        out_dir = os.path.dirname(doc.path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix="gml_edit_", suffix=".gml", dir=out_dir)
        os.close(fd)
        try:
            doc.tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
            os.replace(tmp_path, doc.path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return _result(
            True,
            "Kayıt silindi ve dosya güncellendi.",
            f"backup={backup_path}",
        )
    except Exception as e:
        return _result(False, "Kayıt silinemedi.", str(e))


def _existing_sidecars(shp_path: str) -> list[str]:
    base, _ = os.path.splitext(shp_path)
    exts = [
        ".shp",
        ".shx",
        ".dbf",
        ".prj",
        ".cpg",
        ".sbn",
        ".sbx",
        ".qix",
        ".fix",
        ".xml",
    ]
    return [base + ext for ext in exts if os.path.exists(base + ext)]


def _delete_shp_record(doc: VectorDocument, record_id: int) -> dict:
    try:
        import shapefile  # pyshp
    except Exception as e:
        return _result(
            False,
            "SHP desteği için 'pyshp' modülü gerekli.",
            f"{e}\nKurulum: pip install pyshp",
        )

    target = next((r for r in doc.features if r.row_id == int(record_id)), None)
    if target is None:
        return _result(False, "Silinecek kayıt bulunamadı.")
    if target.source_index is None:
        return _result(False, "SHP kayıt indeksi bulunamadı.")

    shp_path = doc.path
    base, _ = os.path.splitext(shp_path)
    backup_dir = f"{base}.bak"

    try:
        reader = shapefile.Reader(shp_path)
        encoding = getattr(reader, "encoding", "utf-8")
        shape_type = reader.shapeType
        fields_meta = reader.fields[1:]  # DeletionFlag hariç
        records = list(reader.records())
        shapes = list(reader.shapes())
        if hasattr(reader, "close"):
            reader.close()

        idx = int(target.source_index)
        if idx < 0 or idx >= len(records):
            return _result(False, "Silinecek kayıt indeksi geçersiz.")

        # İlk silmede tüm bileşenlerin yedeğini al.
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
            for p in _existing_sidecars(shp_path):
                shutil.copy2(p, os.path.join(backup_dir, os.path.basename(p)))

        out_dir = os.path.dirname(shp_path) or "."
        tmp_dir = tempfile.mkdtemp(prefix="shp_edit_", dir=out_dir)
        tmp_base = os.path.join(tmp_dir, os.path.basename(base))

        writer = shapefile.Writer(tmp_base, shapeType=shape_type, encoding=encoding)
        writer.autoBalance = 1
        for fld in fields_meta:
            writer.field(*fld)

        for i, (shape_obj, rec_obj) in enumerate(zip(shapes, records)):
            if i == idx:
                continue
            writer.shape(shape_obj)
            writer.record(*list(rec_obj))
        writer.close()

        # Yazılmayan sidecar'ları koru (ör. .prj, .cpg)
        for ext in (".prj", ".cpg"):
            src = base + ext
            dst = tmp_base + ext
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            src = tmp_base + ext
            dst = base + ext
            if os.path.exists(src):
                os.replace(src, dst)

        shutil.rmtree(tmp_dir, ignore_errors=True)
        return _result(
            True,
            "Kayıt silindi ve dosya güncellendi.",
            f"backup_dir={backup_dir}",
        )
    except Exception as e:
        return _result(False, "Kayıt silinemedi.", str(e))


def delete_record(doc: VectorDocument, record_id: int) -> dict:
    kind = (doc.kind or "").lower()
    if kind == "gml":
        return _delete_gml_record(doc, record_id)
    if kind == "shp":
        return _delete_shp_record(doc, record_id)
    return _result(False, "Desteklenmeyen doküman türü.", f"kind={doc.kind}")
