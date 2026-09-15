import Link from "next/link";
import type { ReactNode } from "react";

export function Panel({ children, className = "", hover = false }: { children: ReactNode; className?: string; hover?: boolean }) {
  return <div className={`panel ${hover ? "panel-hover" : ""} ${className}`}>{children}</div>;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <h2 className="text-[11px] font-semibold tracking-[0.14em] text-fg-faint uppercase mb-3">{children}</h2>;
}

export function Stat({
  label,
  value,
  accent = "indigo",
}: {
  label: string;
  value: number | string;
  accent?: "indigo" | "cyan" | "violet" | "amber" | "plain";
}) {
  const tone =
    accent === "indigo" ? "text-indigo" :
    accent === "cyan" ? "text-cyan" :
    accent === "violet" ? "text-violet" :
    accent === "amber" ? "text-amber" : "text-fg";
  return (
    <Panel className="px-4 py-3">
      <div className={`text-xl font-semibold tabular-nums ${tone}`}>{typeof value === "number" ? value.toLocaleString() : value}</div>
      <div className="text-[11px] tracking-wide text-fg-faint mt-0.5">{label}</div>
    </Panel>
  );
}

const BADGE_TONES: Record<string, string> = {
  pull_request: "border-indigo/25 text-indigo bg-indigo/[0.07]",
  standalone_commit: "border-violet/25 text-violet bg-violet/[0.07]",
  commit: "border-violet/25 text-violet bg-violet/[0.07]",
  merged: "border-violet/25 text-violet bg-violet/[0.07]",
  open: "border-green/25 text-green bg-green/[0.08]",
  closed: "border-red/20 text-red bg-red/[0.07]",
  "high-p": "border-amber/30 text-amber bg-amber/[0.1]",
  "high-r": "border-violet-deep/40 text-violet-deep bg-violet-deep/[0.12]",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const cls = (tone && BADGE_TONES[tone]) ?? "border-line text-fg-dim bg-surface-alt";
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium tracking-[0.08em] uppercase ${cls}`}>
      {children}
    </span>
  );
}

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1.5 text-sm text-fg-faint hover:text-indigo transition-colors">
      <span aria-hidden="true">←</span>
      {children}
    </Link>
  );
}

export function Shell({ children, width = "max-w-4xl" }: { children: ReactNode; width?: string }) {
  return <main className={`relative z-10 ${width} mx-auto px-6 py-12`}>{children}</main>;
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: {
  children: ReactNode;
  variant?: "primary" | "secondary";
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-lg px-5 py-2.5 text-sm font-medium transition disabled:opacity-45";
  const style =
    variant === "primary"
      ? "bg-gradient-to-r from-indigo to-cyan-deep text-white shadow-sm shadow-indigo/25 hover:shadow-md hover:shadow-indigo/30 hover:-translate-y-px"
      : "border border-line bg-surface text-fg-dim hover:border-indigo/30 hover:text-indigo";
  return (
    <button className={`${base} ${style} ${className}`} {...props}>
      {children}
    </button>
  );
}
