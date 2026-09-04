import Link from "next/link";
import type { ReactNode } from "react";

export function Panel({ children, className = "", hover = false }: { children: ReactNode; className?: string; hover?: boolean }) {
  return <div className={`panel ${hover ? "panel-hover" : ""} ${className}`}>{children}</div>;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <h2 className="text-[11px] font-medium tracking-[0.14em] text-fg-faint uppercase mb-3">{children}</h2>;
}

export function Stat({ label, value, accent = "cyan" }: { label: string; value: number | string; accent?: "cyan" | "violet" | "plain" }) {
  const tone =
    accent === "cyan" ? "text-cyan" : accent === "violet" ? "text-violet" : "text-fg";
  return (
    <Panel className="px-4 py-3">
      <div className={`text-xl font-semibold tabular-nums ${tone}`}>{typeof value === "number" ? value.toLocaleString() : value}</div>
      <div className="text-[11px] tracking-wide text-fg-faint mt-0.5">{label}</div>
    </Panel>
  );
}

const BADGE_TONES: Record<string, string> = {
  pull_request: "border-cyan-deep/35 text-cyan bg-cyan-deep/10",
  standalone_commit: "border-violet-deep/35 text-violet bg-violet-deep/10",
  commit: "border-violet-deep/35 text-violet bg-violet-deep/10",
  merged: "border-violet-deep/35 text-violet bg-violet-deep/10",
  open: "border-green/30 text-green bg-green/10",
  closed: "border-red/25 text-red bg-red/10",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const cls = (tone && BADGE_TONES[tone]) ?? "border-line text-fg-dim bg-white/[0.03]";
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium tracking-[0.08em] uppercase ${cls}`}>
      {children}
    </span>
  );
}

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1.5 text-sm text-fg-faint hover:text-cyan transition-colors">
      <span aria-hidden="true">←</span>
      {children}
    </Link>
  );
}

export function Shell({ children, width = "max-w-4xl" }: { children: ReactNode; width?: string }) {
  return <main className={`relative z-10 ${width} mx-auto px-6 py-12`}>{children}</main>;
}
