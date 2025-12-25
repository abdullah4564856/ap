import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ceramic Stamp Generator",
  description: "Convert SVG to a 3D printable ceramic stamp (STL).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
