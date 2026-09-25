import { Fragment, type ReactNode } from "react";

/**
 * Rendu du corps d'une leçon.
 *
 * Les leçons écrites à la main sont de simples paragraphes ; celles que produit
 * `script/solver/build_lessons.py` contiennent des tableaux, des listes et des blocs
 * `code` (lignes de coups, diagrammes ASCII). Sans ce rendu, tout apparaîtrait en un
 * seul paragraphe et les chiffres seraient illisibles.
 */
export default function LessonBody({ body }: { body: string }) {
  return <div className="mt-2 space-y-3 leading-relaxed text-white/80">{renderBlocks(body)}</div>;
}

function renderBlocks(body: string): ReactNode[] {
  const lines = body.split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(
        <pre
          key={`code-${index}`}
          className="overflow-x-auto rounded-lg border border-white/10 bg-black/40 p-3 text-xs leading-snug text-white/75"
        >
          {code.join("\n")}
        </pre>
      );
      continue;
    }

    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (index < lines.length && lines[index].startsWith("|")) {
        const cells = lines[index]
          .split("|")
          .slice(1, -1)
          .map((cell) => cell.trim());
        if (!cells.every((cell) => /^-+:?$/.test(cell) || cell === "---")) {
          rows.push(cells);
        }
        index += 1;
      }
      const [header, ...rest] = rows;
      blocks.push(
        <div key={`table-${index}`} className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {header?.map((cell, cellIndex) => (
                  <th
                    key={cellIndex}
                    className="border-b border-white/15 px-2 py-1 text-left font-semibold text-white/70"
                  >
                    {inline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rest.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      className={`border-b border-white/5 px-2 py-1 ${
                        cellIndex === 0 ? "text-white/80" : "text-right tabular-nums text-white/70"
                      }`}
                    >
                      {inline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].startsWith("- ")) {
        items.push(lines[index].slice(2));
        index += 1;
      }
      blocks.push(
        <ul key={`list-${index}`} className="list-disc space-y-1 pl-5">
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{inline(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() !== "" &&
      !lines[index].startsWith("```") &&
      !lines[index].startsWith("|") &&
      !lines[index].startsWith("- ")
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(
      <p key={`p-${index}`}>{inline(paragraph.join(" "))}</p>
    );
  }

  return blocks;
}

/** Gras `**x**`, italique `*x*`, code `` `x` `` — sans dépendance externe. */
function inline(text: string): ReactNode[] {
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  const parts = text.split(pattern).filter((part) => part !== "");
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={index} className="rounded bg-white/10 px-1 py-0.5 text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return (
        <em key={index} className="text-white/90">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}
