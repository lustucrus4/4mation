import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

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
  "absolute z-50 max-h-60 w-full overflow-y-auto rounded-lg border border-accent/40 " +
  "bg-midnight py-1 shadow-lg shadow-black/40";

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
  const [openUp, setOpenUp] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const selected = options.find((o) => o.value === value);
  const enabledOptions = options.filter((o) => !o.disabled);

  const close = useCallback(() => {
    setOpen(false);
    setActiveIndex(-1);
  }, []);

  const selectOption = useCallback(
    (option: SelectOption) => {
      if (option.disabled) return;
      onChange(option.value);
      close();
    },
    [onChange, close]
  );

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;
    const rect = rootRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const menuHeight = Math.min(240, enabledOptions.length * 40 + 8);
    setOpenUp(spaceBelow < menuHeight && spaceAbove > spaceBelow);
  }, [open, enabledOptions.length]);

  useEffect(() => {
    if (!open || !listRef.current) return;
    listRef.current.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        close();
      }
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

  const openList = () => {
    if (disabled) return;
    const idx = enabledOptions.findIndex((o) => o.value === value);
    setActiveIndex(idx >= 0 ? idx : 0);
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

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-labelledby={id}
          tabIndex={-1}
          className={`${listBase} ${openUp ? "bottom-full mb-1" : "top-full mt-1"}`}
          style={{
            maxHeight: openUp
              ? `${Math.min(240, rootRef.current?.getBoundingClientRect().top ?? 240) - 8}px`
              : `${Math.min(240, window.innerHeight - (rootRef.current?.getBoundingClientRect().bottom ?? 0) - 8)}px`,
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
        </ul>
      )}
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
