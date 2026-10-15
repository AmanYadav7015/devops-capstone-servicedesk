import type { Stats } from "../types";

interface Props {
  stats: Stats | null;
}

const TILES: { key: keyof Stats; label: string; tone: string }[] = [
  { key: "total", label: "Total tickets", tone: "total" },
  { key: "open", label: "Open", tone: "open" },
  { key: "pending", label: "Pending", tone: "pending" },
  { key: "resolved", label: "Resolved", tone: "resolved" },
  { key: "closed", label: "Closed", tone: "closed" },
  { key: "breachingSla", label: "SLA breached", tone: "breach" },
];

export default function StatsBar({ stats }: Props) {
  return (
    <section className="stats" aria-label="Queue summary">
      {TILES.map((tile) => {
        const value = stats ? stats[tile.key] : null;
        const alert = tile.key === "breachingSla" && (value ?? 0) > 0;
        return (
          <article key={tile.key} className={`stat stat--${tile.tone}${alert ? " stat--alert" : ""}`}>
            <span className="stat__value">{value === null ? "—" : value}</span>
            <span className="stat__label">{tile.label}</span>
          </article>
        );
      })}
    </section>
  );
}
