import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
  title?: string;
}

interface SelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  disabled?: boolean;
  className?: string;
  placeholder?: string;
  "aria-label"?: string;
}

const triggerBase =
  "flex w-full items-center justify-between gap-2 rounded-lg border-2 border-accent " +
  "bg-night px-3 py-2.5 text-left text-sm text-white transition-colors " +
  "hover:border-accent-hover hover:bg-midnight " +
  "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-night";

const listBase =
  "fixed z-[100] overflow-y-auto rounded-lg border border-accent/40 " +
  "bg-midnight py-1 shadow-lg shadow-black/40";

/** Écart entre le déclencheur et la liste. */
const GAP = 4;
/** Hauteur d'une option, pour estimer la place nécessaire (padding inclus). */
const OPTION_HEIGHT = 40;
const MAX_LIST_HEIGHT = 240;

interface ListLayout {
  /** Bord supérieur du déclencheur, en coordonnées écran. */
  anchorTop: number;
  /** Bord inférieur du déclencheur, en coordonnées écran. */
  anchorBottom: number;
  left: number;
  width: number;
  maxHeight: number;
  openUp: boolean;
}

export default function Select({
  id: idProp,
  value,
  onChange,
  options,
  disabled = false,
  className = "",
  placeholder = "Choisir…",
  "aria-label": ariaLabel,
}: SelectProps) {
  const autoId = useId();
  const id = idProp ?? autoId;
  const listId = `${id}-listbox`;

  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [layout, setLayout] = useState<ListLayout | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);

  const selected = options.find((o) => o.value === value);
  const enabledOptions = options.filter((o) => !o.disabled);

  const close = useCallback(() => {
    setOpen(false);
    setActiveIndex(-1);
  }, []);

  /**
   * Position de la liste, mesurée sur le déclencheur. La liste est rendue dans un portail
   * et donc positionnée en `fixed` : elle échappe ainsi à tout `overflow` ou contexte
   * d'empilement d'un ancêtre (une carte avec `backdrop-blur` enferme le `z-index` de ses
   * enfants, et le frère suivant la recouvre).
   */
  const measure = useCallback(() => {
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const desired = Math.min(MAX_LIST_HEIGHT, enabledOptions.length * OPTION_HEIGHT + 8);
    const spaceBelow = window.innerHeight - rect.bottom - GAP;
    const spaceAbove = rect.top - GAP;
    // On n'ouvre vers le haut que si le bas manque vraiment de place et que le haut en a plus.
    const openUp = spaceBelow < desired && spaceAbove > spaceBelow;
    const available = openUp ? spaceAbove : spaceBelow;
    setLayout({
      anchorTop: rect.top,
      anchorBottom: rect.bottom,
      left: rect.left,
      width: rect.width,
      maxHeight: Math.max(OPTION_HEIGHT, Math.min(desired, available)),
      openUp,
    });
  }, [enabledOptions.length]);

  // Filet de sécurité : le déclencheur se désactive pendant que la liste est ouverte
  // (partie « occupée »), on referme plutôt que de laisser une liste orpheline.
  useEffect(() => {
    if (disabled && open) close();
  }, [disabled, open, close]);

  useEffect(() => {
    if (!open) {
      setLayout(null);
      return;
    }
    measure();
    // `capture: true` : on suit aussi le défilement des conteneurs internes, pas seulement
    // de la fenêtre. La liste étant en `fixed`, elle ne suivrait pas le déclencheur seule.
    const onReflow = () => measure();
    window.addEventListener("scroll", onReflow, true);
    window.addEventListener("resize", onReflow);
    return () => {
      window.removeEventListener("scroll", onReflow, true);
      window.removeEventListener("resize", onReflow);
    };
  }, [open, measure]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    listRef.current.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      // La liste vit dans un portail : elle n'est PAS contenue dans `rootRef`, il faut
      // donc la tester séparément, sinon un clic sur une option la refermerait avant
      // que le clic n'atteigne l'option.
      if (rootRef.current?.contains(target)) return;
      if (listRef.current?.contains(target)) return;
      close();
    };
    const onEscape = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open, close]);

  useEffect(() => {
    if (!open || activeIndex < 0 || !listRef.current) return;
    const items = Array.from(listRef.current.children) as HTMLElement[];
    const item = items.find((el) => el.dataset.active === "true");
    item?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  const selectOption = useCallback(
    (option: SelectOption) => {
      if (option.disabled) return;
      onChange(option.value);
      close();
    },
    [onChange, close]
  );

  const openList = () => {
    if (disabled) return;
    const idx = enabledOptions.findIndex((o) => o.value === value);
    setActiveIndex(idx >= 0 ? idx : 0);
    measure();
    setOpen(true);
  };

  const onTriggerKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    switch (e.key) {
      case "ArrowDown":
      case "ArrowUp":
      case "Enter":
      case " ":
        e.preventDefault();
        openList();
        break;
      default:
        break;
    }
  };

  const onListKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    if (!enabledOptions.length) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % enabledOptions.length);
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex((i) => (i <= 0 ? enabledOptions.length - 1 : i - 1));
        break;
      case "Home":
        e.preventDefault();
        setActiveIndex(0);
        break;
      case "End":
        e.preventDefault();
        setActiveIndex(enabledOptions.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (activeIndex >= 0) selectOption(enabledOptions[activeIndex]);
        break;
      case "Escape":
        e.preventDefault();
        close();
        break;
      case "Tab":
        close();
        break;
      default:
        break;
    }
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        id={id}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        className={triggerBase}
        onClick={() => (open ? close() : openList())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="min-w-0 truncate">{selected?.label ?? placeholder}</span>
        <Chevron open={open} />
      </button>

      {open && layout
        ? createPortal(
            <ul
              ref={listRef}
              id={listId}
              role="listbox"
              aria-labelledby={id}
              tabIndex={-1}
              className={listBase}
              style={{
                left: layout.left,
                width: layout.width,
                maxHeight: layout.maxHeight,
                ...(layout.openUp
                  ? { bottom: window.innerHeight - layout.anchorTop + GAP }
                  : { top: layout.anchorBottom + GAP }),
              }}
              onKeyDown={onListKeyDown}
            >
              {options.map((option) => {
                const enabledIdx = enabledOptions.indexOf(option);
                const isSelected = option.value === value;
                const isActive = enabledIdx === activeIndex;
                return (
                  <li
                    key={option.value}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={option.disabled || undefined}
                    data-active={isActive ? "true" : undefined}
                    title={option.title}
                    className={[
                      "cursor-pointer px-3 py-2 text-sm transition-colors",
                      option.disabled
                        ? "cursor-not-allowed text-white/30"
                        : isSelected
                          ? "bg-accent/20 font-semibold text-accent"
                          : isActive
                            ? "bg-accent/10 text-white"
                            : "text-white/85 hover:bg-white/10",
                    ].join(" ")}
                    onMouseEnter={() => {
                      if (!option.disabled && enabledIdx >= 0) setActiveIndex(enabledIdx);
                    }}
                    onClick={() => selectOption(option)}
                  >
                    {option.label}
                  </li>
                );
              })}
            </ul>,
            document.body
          )
        : null}
    </div>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      className={`h-4 w-4 shrink-0 text-accent transition-transform ${open ? "rotate-180" : ""}`}
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
        clipRule="evenodd"
      />
    </svg>
  );
}
