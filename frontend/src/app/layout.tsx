import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "story-engine v2",
  description: "Multi-agent narrative system with persistent memory",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased min-h-screen bg-surface text-slate-200">
        {children}
      </body>
    </html>
  );
}
