import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function fmtDate(d: string) {
  const dt = new Date(d.replace(" ", "T"));
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default async function UpcomingPage() {
  const matches = await api.upcoming(30).catch(() => []);

  return (
    <div>
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">Calendrier</p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">Matchs à venir</h1>
        <p className="mt-2 max-w-2xl text-mist">
          Les prochaines rencontres programmées, avec leur prédiction. Ouvre le dossier complet
          d&apos;un match pour la physionomie, la lecture tactique et tous les angles.
        </p>
      </header>

      {matches.length === 0 ? (
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Aucun match programmé pour l&apos;instant. Ajoute des rencontres dans{" "}
          <code className="font-mono text-chalk">data/fixtures.json</code> pour les voir apparaître ici.
        </div>
      ) : (
        <div className="space-y-3">
          {matches.map((m, i) => {
            const p = m.prediction;
            return (
              <Link
                key={i}
                href={`/match?home=${encodeURIComponent(m.home_team)}&away=${encodeURIComponent(m.away_team)}`}
                className="block rounded-card border border-line bg-slate p-4 transition-colors hover:border-mist"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-28 shrink-0 text-xs text-mist">
                      {m.stage && <div className="mb-0.5 font-mono uppercase tracking-wider text-signal">{m.stage}</div>}
                      {fmtDate(m.date)}
                    </div>
                    <div className="font-display text-lg font-semibold">
                      <span className="text-pitch">{m.home_team}</span>
                      <span className="mx-2 text-mist">—</span>
                      <span className="text-clay">{m.away_team}</span>
                    </div>
                  </div>
                  {p && (
                    <div className="flex items-center gap-3 font-mono text-xs tabular">
                      <Prob label="1" value={p.markets.home_win} />
                      <Prob label="N" value={p.markets.draw} />
                      <Prob label="2" value={p.markets.away_win} />
                      <span className="ml-2 text-pitch">Dossier →</span>
                    </div>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Prob({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded border border-line px-2 py-1 text-mist">
      {label} <span className="text-chalk">{value.toFixed(0)}%</span>
    </span>
  );
}
