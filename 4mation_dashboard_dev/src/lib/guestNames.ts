/** Prénom français + genre pour le suffixe invité / invitée. */
export type GuestNameEntry = {
  name: string;
  gender: "m" | "f";
};

/** Liste étendue de prénoms français courants. */
export const FRENCH_GUEST_NAMES: GuestNameEntry[] = [
  { name: "Paul", gender: "m" },
  { name: "Pierre", gender: "m" },
  { name: "Jacques", gender: "m" },
  { name: "Michel", gender: "m" },
  { name: "Philippe", gender: "m" },
  { name: "Alain", gender: "m" },
  { name: "Bernard", gender: "m" },
  { name: "Christophe", gender: "m" },
  { name: "Nicolas", gender: "m" },
  { name: "François", gender: "m" },
  { name: "Laurent", gender: "m" },
  { name: "Olivier", gender: "m" },
  { name: "David", gender: "m" },
  { name: "Thomas", gender: "m" },
  { name: "Julien", gender: "m" },
  { name: "Alexandre", gender: "m" },
  { name: "Antoine", gender: "m" },
  { name: "Maxime", gender: "m" },
  { name: "Lucas", gender: "m" },
  { name: "Hugo", gender: "m" },
  { name: "Louis", gender: "m" },
  { name: "Gabriel", gender: "m" },
  { name: "Arthur", gender: "m" },
  { name: "Jules", gender: "m" },
  { name: "Léo", gender: "m" },
  { name: "Raphaël", gender: "m" },
  { name: "Adam", gender: "m" },
  { name: "Nathan", gender: "m" },
  { name: "Ethan", gender: "m" },
  { name: "Noah", gender: "m" },
  { name: "Mathis", gender: "m" },
  { name: "Clément", gender: "m" },
  { name: "Benjamin", gender: "m" },
  { name: "Vincent", gender: "m" },
  { name: "Sébastien", gender: "m" },
  { name: "Guillaume", gender: "m" },
  { name: "Étienne", gender: "m" },
  { name: "Baptiste", gender: "m" },
  { name: "Florian", gender: "m" },
  { name: "Romain", gender: "m" },
  { name: "Adrien", gender: "m" },
  { name: "Kévin", gender: "m" },
  { name: "Yann", gender: "m" },
  { name: "Marc", gender: "m" },
  { name: "Henri", gender: "m" },
  { name: "André", gender: "m" },
  { name: "René", gender: "m" },
  { name: "Georges", gender: "m" },
  { name: "Charles", gender: "m" },
  { name: "Jean", gender: "m" },
  { name: "Marie", gender: "f" },
  { name: "Nathalie", gender: "f" },
  { name: "Isabelle", gender: "f" },
  { name: "Sylvie", gender: "f" },
  { name: "Catherine", gender: "f" },
  { name: "Françoise", gender: "f" },
  { name: "Monique", gender: "f" },
  { name: "Sophie", gender: "f" },
  { name: "Julie", gender: "f" },
  { name: "Camille", gender: "f" },
  { name: "Laura", gender: "f" },
  { name: "Sarah", gender: "f" },
  { name: "Léa", gender: "f" },
  { name: "Manon", gender: "f" },
  { name: "Chloé", gender: "f" },
  { name: "Emma", gender: "f" },
  { name: "Jade", gender: "f" },
  { name: "Louise", gender: "f" },
  { name: "Alice", gender: "f" },
  { name: "Inès", gender: "f" },
  { name: "Lina", gender: "f" },
  { name: "Zoé", gender: "f" },
  { name: "Clara", gender: "f" },
  { name: "Juliette", gender: "f" },
  { name: "Élise", gender: "f" },
  { name: "Anaïs", gender: "f" },
  { name: "Margot", gender: "f" },
  { name: "Océane", gender: "f" },
  { name: "Pauline", gender: "f" },
  { name: "Valérie", gender: "f" },
  { name: "Sandrine", gender: "f" },
  { name: "Stéphanie", gender: "f" },
  { name: "Caroline", gender: "f" },
  { name: "Aurélie", gender: "f" },
  { name: "Céline", gender: "f" },
  { name: "Virginie", gender: "f" },
  { name: "Hélène", gender: "f" },
  { name: "Brigitte", gender: "f" },
  { name: "Martine", gender: "f" },
  { name: "Christine", gender: "f" },
  { name: "Patricia", gender: "f" },
  { name: "Véronique", gender: "f" },
  { name: "Dominique", gender: "f" },
  { name: "Anne", gender: "f" },
  { name: "Jeanne", gender: "f" },
  { name: "Charlotte", gender: "f" },
  { name: "Amélie", gender: "f" },
  { name: "Émilie", gender: "f" },
  { name: "Lucie", gender: "f" },
  { name: "Margaux", gender: "f" },
  { name: "Elodie", gender: "f" },
  { name: "Maëlys", gender: "f" },
  { name: "Louna", gender: "f" },
  { name: "Ambre", gender: "f" },
  { name: "Lilou", gender: "f" },
  { name: "Romane", gender: "f" },
  { name: "Capucine", gender: "f" },
  { name: "Faustine", gender: "f" },
];

const GUEST_SUFFIX = { m: "invité", f: "invitée" } as const;
const MAX_GUEST_NAME_LEN = 24;

function capitalizeFirst(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

/** Ex. « Paul (invité) » ou « Jeanne (invitée) ». */
export function formatGuestDisplayName(firstName: string, gender: "m" | "f"): string {
  const prenom = capitalizeFirst(firstName.trim());
  const suffix = GUEST_SUFFIX[gender];
  return `${prenom} (${suffix})`;
}

export function isGenericGuestName(name: string): boolean {
  const normalized = name.trim().toLowerCase();
  return (
    !normalized ||
    normalized === "invité" ||
    normalized === "invitée" ||
    normalized === "invite" ||
    normalized === "invitee"
  );
}

/** Tire un pseudo invité aléatoire (≤ 24 caractères). */
export function generateRandomGuestName(): string {
  const pool = [...FRENCH_GUEST_NAMES];
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const index = Math.floor(Math.random() * pool.length);
    const entry = pool.splice(index, 1)[0] ?? FRENCH_GUEST_NAMES[0];
    const formatted = formatGuestDisplayName(entry.name, entry.gender);
    if (formatted.length <= MAX_GUEST_NAME_LEN) {
      return formatted;
    }
  }
  return "Léo (invité)";
}

export function ensureGuestName(name?: string | null): string {
  const trimmed = name?.trim() ?? "";
  if (!isGenericGuestName(trimmed)) {
    return trimmed.slice(0, MAX_GUEST_NAME_LEN);
  }
  return generateRandomGuestName();
}
