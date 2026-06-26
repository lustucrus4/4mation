import Button from "../ui/Button";

interface MoveNavigatorProps {
  moveIndex: number;
  maxMove: number;
  onChange: (index: number) => void;
  disabled?: boolean;
  /** Masque uniquement ⏮ (début de partie). */
  hideStart?: boolean;
}

export default function MoveNavigator({
  moveIndex,
  maxMove,
  onChange,
  disabled = false,
  hideStart = false,
}: MoveNavigatorProps) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {!hideStart && (
        <Button variant="ghost" onClick={() => onChange(0)} disabled={disabled || moveIndex === 0}>
          ⏮
        </Button>
      )}
      <Button
        variant="ghost"
        onClick={() => onChange(Math.max(0, moveIndex - 1))}
        disabled={disabled || moveIndex === 0}
      >
        ◀
      </Button>
      <span className="min-w-[5rem] text-center text-sm text-white/70">
        {moveIndex} / {maxMove}
      </span>
      <Button
        variant="ghost"
        onClick={() => onChange(Math.min(maxMove, moveIndex + 1))}
        disabled={disabled || moveIndex >= maxMove}
      >
        ▶
      </Button>
      <Button
        variant="ghost"
        onClick={() => onChange(maxMove)}
        disabled={disabled || moveIndex >= maxMove}
      >
        ⏭
      </Button>
    </div>
  );
}
