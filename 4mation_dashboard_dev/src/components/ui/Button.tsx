import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-bold " +
  "transition-[transform,background-color,opacity] duration-150 disabled:opacity-50 " +
  "disabled:cursor-not-allowed cursor-pointer select-none";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-deep hover:bg-accent-hover hover:-translate-y-px",
  secondary: "bg-warn text-night hover:brightness-95 hover:-translate-y-px",
  ghost: "bg-transparent text-accent border border-accent hover:bg-accent/10",
};

export default function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...rest}>
      {children}
    </button>
  );
}
