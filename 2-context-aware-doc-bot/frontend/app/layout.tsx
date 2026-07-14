import type { Metadata } from "next";
import "./globals.css";

// Note: this scaffold originally used `next/font/google` (Geist/Geist Mono),
// which fetches font files from fonts.googleapis.com at build time. That
// host is unreachable in this sandbox (network egress to Google Fonts is
// blocked), which made `next build` fail outright. Falling back to the
// system font stack keeps the same CSS variable names so nothing downstream
// needs to change, and avoids a hard network dependency at build time.

export const metadata: Metadata = {
  title: "Context-Aware Doc Bot",
  description: "Index a GitHub repo and chat with it.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased bg-gradient-to-br from-blue-950 to-black bg-fixed">
      <body className="h-full flex flex-col overflow-hidden">{children}</body>
    </html>
  );
}
