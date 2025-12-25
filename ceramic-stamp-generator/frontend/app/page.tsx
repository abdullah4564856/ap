\
"use client";

import React, { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

const STLPreview = dynamic(() => import("../components/STLPreview"), { ssr: false });

type Mode = "raised" | "engraved";
type Size = 25 | 30 | 40;

function b64ToJson(b64: string | null): any | null {
  if (!b64) return null;
  try {
    const txt = atob(b64);
    return JSON.parse(txt);
  } catch {
    return null;
  }
}

export default function Page() {
  const [file, setFile] = useState<File | null>(null);

  const [size, setSize] = useState<Size>(30);
  const [mode, setMode] = useState<Mode>("raised");

  const [baseMm, setBaseMm] = useState<number>(7);
  const [reliefMm, setReliefMm] = useState<number>(2.2);
  const [minLineMm, setMinLineMm] = useState<number>(1.4);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [meta, setMeta] = useState<any | null>(null);

  const [stlUrl, setStlUrl] = useState<string>("");
  const downloadName = useMemo(() => {
    if (!file) return "stamp.stl";
    const stem = file.name.replace(/\.svg$/i, "");
    return `${stem}_${size}mm_${mode}.stl`;
  }, [file, size, mode]);

  async function onGenerate() {
    setError("");
    setMeta(null);
    if (!file) {
      setError("ارفع ملف SVG أولاً.");
      return;
    }

    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);

      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const qs = new URLSearchParams({
        size_mm: String(size),
        mode,
        base_mm: String(baseMm),
        relief_mm: String(reliefMm),
        min_line_mm: String(minLineMm),
      });

      const res = await fetch(`${apiBase}/api/generate?${qs.toString()}`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        const msg = data?.detail || `فشل التحويل (HTTP ${res.status})`;
        throw new Error(msg);
      }

      const metaObj = b64ToJson(res.headers.get("X-Stamp-Meta"));
      setMeta(metaObj);

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setStlUrl(url);
    } catch (e: any) {
      setError(e?.message || "صار خطأ غير متوقع.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="inline" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h1 className="h1">مولّد ختم خزفي (SVG → STL)</h1>
          <div className="muted">
            ارفع SVG نظيف (Vector فقط) وطلع STL جاهز للطباعة ثلاثية الأبعاد.
          </div>
        </div>
        <div className="pill">MVP</div>
      </div>

      <div className="row">
        <section className="card">
          <label>ملف SVG</label>
          <input
            type="file"
            accept=".svg,image/svg+xml"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <div className="hr" />

          <label>المقاس</label>
          <select value={size} onChange={(e) => setSize(Number(e.target.value) as Size)}>
            <option value={25}>25 مم</option>
            <option value={30}>30 مم</option>
            <option value={40}>40 مم</option>
          </select>

          <div style={{ height: 10 }} />

          <label>النمط</label>
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
            <option value="raised">بارز (Raised)</option>
            <option value="engraved">محفور (Engraved)</option>
          </select>

          <div className="hr" />

          <details>
            <summary>إعدادات متقدمة</summary>
            <div style={{ height: 12 }} />

            <label>سماكة القاعدة (mm)</label>
            <input
              type="number"
              step={0.1}
              value={baseMm}
              onChange={(e) => setBaseMm(Number(e.target.value))}
            />

            <div style={{ height: 10 }} />

            <label>ارتفاع البروز/الحفر (mm)</label>
            <input
              type="number"
              step={0.1}
              value={reliefMm}
              onChange={(e) => setReliefMm(Number(e.target.value))}
            />

            <div style={{ height: 10 }} />

            <label>أقل سماكة للخط (mm)</label>
            <input
              type="number"
              step={0.1}
              value={minLineMm}
              onChange={(e) => setMinLineMm(Number(e.target.value))}
            />

            <div className="small" style={{ marginTop: 10 }}>
              نصيحة: لو طباعة FDM تعطيك خطوط ضعيفة، ارفع <b>أقل سماكة للخط</b>.
            </div>
          </details>

          <div className="hr" />

          <button onClick={onGenerate} disabled={busy}>
            {busy ? "جاري التوليد..." : "ولّد الختم"}
          </button>

          {error ? <div className="error" style={{ marginTop: 12 }}>{error}</div> : null}

          {meta?.warnings?.length ? (
            <div className="warn" style={{ marginTop: 12 }}>
              <b>تحذيرات:</b>
              {"\n"}
              {meta.warnings.map((w: string, i: number) => `- ${w}`).join("\n")}
            </div>
          ) : null}

          {meta ? (
            <div className="small" style={{ marginTop: 12, lineHeight: 1.6 }}>
              <b>تقرير الأبعاد:</b>
              <div>المقاس: {meta.size_mm}mm</div>
              <div>القاعدة: {meta.base_mm}mm</div>
              <div>البروز/الحفر: {meta.relief_mm}mm</div>
              <div>bbox: {Array.isArray(meta.bbox_mm) ? meta.bbox_mm.map((n: number)=>n.toFixed(2)).join(", ") : ""}</div>
            </div>
          ) : null}

          {stlUrl ? (
            <div style={{ marginTop: 12 }}>
              <a className="link" href={stlUrl} download={downloadName}>تحميل STL</a>
            </div>
          ) : null}
        </section>

        <section className="card">
          <div className="inline" style={{ justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 800 }}>معاينة ثلاثية الأبعاد</div>
              <div className="muted">بعد التوليد، بيظهر STL هنا.</div>
            </div>
            {stlUrl ? <span className="pill">STL جاهز</span> : <span className="pill">بانتظار ملف</span>}
          </div>

          <div style={{ height: 12 }} />
          <div className="previewBox">
            <STLPreview stlUrl={stlUrl} />
          </div>

          <div className="small" style={{ marginTop: 10 }}>
            تدوير: سحب بالماوس • زوم: عجلة الماوس
          </div>
        </section>
      </div>

      <div style={{ marginTop: 18 }} className="muted">
        مشاكل شائعة: SVG فيه صور داخلية / خطوط نحيفة جدًا / نص غير محول لمسارات. صدّر كـ “Paths/Outline”.
      </div>
    </main>
  );
}
