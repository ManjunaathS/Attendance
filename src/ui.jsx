import React from "react";
import { Search, X, Check } from "lucide-react";
export const cn = (...a) => a.filter(Boolean).join(" ");
export function Button({
  children,
  onClick,
  type = "button",
  tone = "soft",
  disabled = false,
  className = "",
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={cn("btn", `btn-${tone}`, className)}
    >
      {children}
    </button>
  );
}
export function Badge({ children, tone = "gray" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function Panel({ children, className = "" }) {
  return <section className={cn("panel", className)}>{children}</section>;
}
export function Heading({
  title,
  description,
  eyebrow = "WORKSPACE",
  actions,
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}
export function SectionHead({ title, subtitle, action }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
export function Modal({
  title,
  description,
  onClose,
  children,
  className = "",
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section className={`modal ${className}`}>
        <button className="modal-x" onClick={onClose} aria-label="Close">
          <X size={17} />
        </button>
        <div className="eyebrow">ATTEND · REVIEW</div>
        <h2>{title}</h2>
        {description && <p className="muted">{description}</p>}
        {children}
      </section>
    </div>
  );
}
export function Toast({ text, onClose }) {
  if (!text) return null;
  return (
    <div className="toast">
      <span>
        <Check size={15} />
      </span>
      <div>{text}</div>
      <button onClick={onClose}>
        <X size={15} />
      </button>
    </div>
  );
}
export function Empty({ children = "Nothing to show yet." }) {
  return (
    <div className="empty-state">
      <span>
        <Search size={18} />
      </span>
      <p>{children}</p>
    </div>
  );
}
export function Notice({ children }) {
  return <div className="notice-box">{children}</div>;
}
export function Stat({ label, value, note, icon: Icon, tone = "purple" }) {
  return (
    <div className="stat-card">
      <div className="stat-label">
        {label}
        <span className={`stat-icon ${tone}`}>
          <Icon size={16} />
        </span>
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
export const roleName = {
  EMPLOYEE: "Employee",
  MANAGER: "Manager",
  HR: "HR",
  ADMIN: "Admin",
};
export const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const monthISO = () => todayISO().slice(0, 7);
export const fmtDate = (
  v,
  o = { day: "numeric", month: "short", year: "numeric" },
) =>
  v
    ? new Intl.DateTimeFormat("en-IN", o).format(
        new Date(`${String(v).slice(0, 10)}T12:00:00`),
      )
    : "—";
export const mins = (n) =>
  `${Math.floor((n || 0) / 60)}h ${String((n || 0) % 60).padStart(2, "0")}m`;
