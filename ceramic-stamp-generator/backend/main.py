
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

from converter.convert import convert_svg_to_stl, ConvertError

ALLOWED_SIZES = {25, 30, 40}
ALLOWED_MODES = {"raised", "engraved"}

app = FastAPI(title="Ceramic Stamp Generator API", version="0.1.0")

# Dev-friendly CORS (compose runs on localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _friendly_http_error(detail: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/generate")
async def generate(
    file: UploadFile = File(...),
    size_mm: int = Query(30, description="Stamp size in mm", enum=[25, 30, 40]),
    mode: Literal["raised", "engraved"] = Query("raised"),
    base_mm: float = Query(7.0, ge=2.0, le=20.0),
    relief_mm: float = Query(2.2, ge=0.6, le=6.0),
    min_line_mm: float = Query(1.4, ge=0.4, le=4.0),
):
    if size_mm not in ALLOWED_SIZES:
        raise _friendly_http_error("Invalid size. Allowed sizes: 25, 30, 40 mm.")
    if mode not in ALLOWED_MODES:
        raise _friendly_http_error("Invalid mode. Allowed: raised, engraved.")

    if not file.filename.lower().endswith(".svg"):
        raise _friendly_http_error("Please upload an SVG file (.svg).")

    svg_bytes = await file.read()
    if not svg_bytes or len(svg_bytes) < 50:
        raise _friendly_http_error("The uploaded file is empty or too small to be a valid SVG.")

    # Convert
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out_stl = td / "stamp.stl"
        try:
            report = convert_svg_to_stl(
                svg_bytes,
                out_stl,
                size_mm=float(size_mm),
                mode=str(mode),
                base_mm=float(base_mm),
                relief_mm=float(relief_mm),
                min_line_mm=float(min_line_mm),
            )
        except ConvertError as e:
            raise _friendly_http_error(str(e), status_code=400)
        except Exception:
            raise _friendly_http_error("Unexpected error while converting. Try simplifying the SVG and retry.", status_code=500)

        # Encode metadata into headers (base64 JSON to avoid header charset issues)
        meta = {
            "size_mm": report.size_mm,
            "base_mm": report.base_mm,
            "relief_mm": report.relief_mm,
            "mode": report.mode,
            "bbox_mm": report.bbox_mm,
            "approx_area_mm2": report.approx_area_mm2,
            "warnings": report.warnings,
        }
        meta_b64 = base64.b64encode(json.dumps(meta).encode("utf-8")).decode("ascii")

        headers = {
            "X-Stamp-Meta": meta_b64,
            "X-Stamp-Warnings": base64.b64encode(json.dumps(report.warnings).encode("utf-8")).decode("ascii"),
        }

        download_name = Path(file.filename).stem + f"_{size_mm}mm_{mode}.stl"
        return FileResponse(
            path=str(out_stl),
            media_type="model/stl",
            filename=download_name,
            headers=headers,
        )

@app.get("/api/meta-help")
def meta_help():
    return JSONResponse(
        {
            "how_to_read": "Read X-Stamp-Meta header (base64 JSON). Example in JS: atob(res.headers.get('X-Stamp-Meta'))",
            "fields": ["bbox_mm", "warnings", "approx_area_mm2", "size_mm", "base_mm", "relief_mm", "mode"],
        }
    )
