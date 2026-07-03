import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Engineer Path",
  description: "AI Chat and Context-Aware Doc Bot demos.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-gradient-to-br from-blue-950 to-black">
        {children}
      </body>
    </html>
  );
}
