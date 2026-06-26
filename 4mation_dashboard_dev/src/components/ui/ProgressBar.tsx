interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  indeterminate?: boolean;
}

export default function ProgressBar({
  value,
  max = 100,
  label,
  indeterminate = false,
}: ProgressBarProps) {
  const pct = indeterminate ? 100 : Math.max(0, Math.min(100, (value / max) * 100));

  return (
    <div className="space-y-2">
      {label ? <p className="text-sm text-white/60">{label}</p> : null}
      <div
        className="h-2.5 overflow-hidden rounded-full bg-white/10"
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "Progression"}
      >
        <div
          className={`h-full rounded-full bg-accent ${
            indeterminate ? "animate-progress-indeterminate w-1/3" : "transition-all duration-300 ease-out"
          }`}
          style={indeterminate ? undefined : { width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
