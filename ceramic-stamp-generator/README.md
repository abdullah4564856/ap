\
# Ceramic Stamp Generator (MVP)

Full-stack MVP that converts an uploaded **SVG** into a **3D printable STL** ceramic stamp.

## Tech
- Frontend: Next.js (App Router), single-page UI (Arabic labels, RTL)
- Backend: FastAPI (`POST /api/generate`)
- Converter engine: `converter/convert.py` (SVG → Shapely → Trimesh → STL)

> Note: Engraved mode uses boolean subtraction when OpenSCAD is available. In this MVP Docker image, OpenSCAD is **not** installed, so engraved mode falls back to a safe approximation and returns a warning. Raised mode works end-to-end.

---

## Run locally (one command)

### Prereqs
- Docker + Docker Compose

### Start
```bash
docker compose up --build
```

Then open:
- Frontend: http://localhost:3000  
- Backend health: http://localhost:8000/api/health

---

## API

### `POST /api/generate`
- `multipart/form-data`
  - `file`: SVG
- Query params:
  - `size_mm` (default `30`, allowed `25|30|40`)
  - `mode` (default `raised`, allowed `raised|engraved`)
  - `base_mm` (default `7`)
  - `relief_mm` (default `2.2`)
  - `min_line_mm` (default `1.4`)

Returns:
- STL file download
- Metadata headers:
  - `X-Stamp-Meta`: base64(JSON) dimension report + warnings

Example (JS):
```js
const meta = JSON.parse(atob(res.headers.get("X-Stamp-Meta")));
console.log(meta.warnings);
```

---

## Project layout
- `backend/` FastAPI app
- `frontend/` Next.js app (single page)
- `converter/` conversion engine + requirements

---

## Tips for clean SVGs
- Export vector-only (no embedded images)
- Convert text to outlines/paths
- Avoid curves/arcs for MVP engine; flatten/approximate curves into line segments if possible
- If printing on FDM, increase **min_line_mm** if the preview shows thin strokes
