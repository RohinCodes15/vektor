import * as motion from "motion/react-client";
import type { HTMLMotionProps } from "motion/react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Button({ variant = "primary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  return <button className={`button button-${variant} ${className}`} {...props} />;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "positive" | "warning" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Panel({ className = "", ...props }: HTMLMotionProps<"section">) {
  return <motion.section className={`panel ${className}`} initial={false} whileInView={{ y: [3, 0] }} viewport={{ once: true, amount: 0.15 }} {...props} />;
}

export function Field({ label, id, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string; hint?: string }) {
  return <div className="field"><label htmlFor={id}>{label}</label><input id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...props} />{hint && <p id={`${id}-hint`} className="muted text-xs">{hint}</p>}</div>;
}

export function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Panel className="metric-card" aria-label={label}><h3>{label}</h3><p className="metric-value">{value}</p><p className="metric-detail muted">{detail}</p></Panel>;
}
