import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export default function Card({ className = "", children, ...rest }: CardProps) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
