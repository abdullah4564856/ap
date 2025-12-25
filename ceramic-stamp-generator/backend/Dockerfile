\
FROM python:3.11-slim

WORKDIR /app

# System deps: OpenSCAD optional (for watertight booleans). We keep it optional for MVP.
# Shapely needs GEOS; wheels include it, so no apt needed on slim for typical platforms.
RUN pip install --no-cache-dir --upgrade pip

COPY converter /app/converter
COPY backend /app/backend

RUN pip install --no-cache-dir -r /app/backend/requirements.txt

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
