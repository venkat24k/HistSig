import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Digital Ghost",
  description: "Browse candidate historical events mined from a GitHub repository's history.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="ambient-grade min-h-full flex flex-col">
        <header className="relative z-20 border-b border-line-soft/70">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
            <Link href="/" className="group flex items-center gap-2.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-cyan-deep opacity-70 group-hover:animate-ping" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan" />
              </span>
              <span className="text-sm font-medium tracking-tight">Digital Ghost</span>
              <span className="text-[10px] tracking-[0.16em] text-fg-faint uppercase border border-line rounded px-1.5 py-0.5">
                HistSig
              </span>
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-fg-faint hover:text-fg-dim transition-colors"
            >
              Mining Software Repositories
            </a>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
