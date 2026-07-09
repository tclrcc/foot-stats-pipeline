import Link from "next/link";
import { clubsExtra, MatchDetail, MatchGoal } from "@/lib/api";

export const dynamic = "force-dynamic";

function fmtDate(d: string) {
  const dt = new Date(d.replace(" ", "T"));
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function minuteLabel(g: MatchGoal) {
  if (g.minute == null) return "?";
  return g.extra ? `${g.minute}+${g.extra}'` : `${g.minute}'`;
}

function goalMark(detail: string | null) {
  if (detail === "Penalty") return " (pen.)";
  if (detail === "Own Goal") return " (csc)";
  return "";
}

export default async function ClubMatchPage({ params }: { params: { id: string } }) {
  const detail = await clubsExtra.matchDetail(Number(params.id)).catch(() => null);

  if (!detail) {
    return (
      <div>
        <BackLink />
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Résumé indisponible pour ce match (id inconnu de l&apos;API, ou clé API absente côté serveur).
        </div>
      </div>
    );
  }

  const d = detail;
  const goals = d.events.goals;
  const reds = d.events.cards;

  return (
    <div>
      <BackLink />

      {/* En-tête score */}
      <div className="rounded-card border border-line bg-slate p-6">
        <div className="mb-3 flex flex-wrap items-center justify-center gap-2 text-xs text-mist">
          {d.round && <span className="rounded border border-line px-2 py-0.5 font-mono text-signal">{d.round}</span>}
          <span>{d.league_name}{d.season ? ` · ${d.season}-${String(d.season + 1).slice(-2)}` : ""}</span>
          <span>· {fmtDate(d.date)}</span>
          {d.venue && <span>· {d.venue}{d.city ? ` (${d.city})` : ""}</span>}
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="text-right font-display text-xl font-bold text-pitch sm:text-2xl">{d.home_team}</div>
          <div className="text-center">
            <div className="rounded-md bg-ink px-4 py-2 font-mono text-3xl font-bold tabular text-chalk">
              {d.home_score}–{d.away_score}
            </div>
            {d.halftime.home != null && (
              <div className="mt-1 font-mono text-xs tabular text-mist">
                mi-temps {d.halftime.home}–{d.halftime.away}
              </div>
            )}
          </div>
          <div className="font-display text-xl font-bold text-clay sm:text-2xl">{d.away_team}</div>
        </div>
      </div>

      {/* Buteurs */}
      <div className="mt-6 rounded-card border border-line bg-slate p-5">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">Buteurs</h2>
        {goals.length === 0 ? (
          <p className="text-center text-sm text-mist">Aucun but dans ce match.</p>
        ) : (
          <div className="space-y-1.5">
            {goals.map((g, i) => (
              <div key={i} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-sm">
                <div className="text-right">
                  {g.side === "home" && (
                    <span>
                      <span className="font-medium text-chalk">{g.player}{goalMark(g.detail)}</span>
                      {g.assist && <span className="text-xs text-mist"> — passe {g.assist}</span>}
                    </span>
                  )}
                </div>
                <span className={`w-14 rounded px-1.5 py-0.5 text-center font-mono text-xs tabular ${g.side === "home" ? "bg-pitch/15 text-pitch" : "bg-clay/15 text-clay"}`}>
                  {minuteLabel(g)} ⚽
                </span>
                <div>
                  {g.side === "away" && (
                    <span>
                      <span className="font-medium text-chalk">{g.player}{goalMark(g.detail)}</span>
                      {g.assist && <span className="text-xs text-mist"> — passe {g.assist}</span>}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {reds.length > 0 && (
          <div className="mt-4 border-t border-line pt-3">
            {reds.map((c, i) => (
              <div key={i} className="text-center text-sm">
                <span className="mr-1.5 inline-block h-3 w-2.5 rounded-[2px] bg-clay align-middle" />
                <span className="font-mono text-xs tabular text-mist">{minuteLabel(c)}</span>{" "}
                <span className="text-chalk">{c.player}</span>{" "}
                <span className="text-xs text-mist">({c.side === "home" ? d.home_team : d.away_team}) — carton rouge</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Compositions */}
      {d.lineups && (
        <div className="mt-6 rounded-card border border-line bg-slate p-5">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-mist">Compositions</h2>
          <div className="grid gap-5 sm:grid-cols-2">
            {(["home", "away"] as const).map((side) => {
              const lu = d.lineups![side];
              return (
                <div key={side} className="rounded-md border border-line bg-ink/40 p-4">
                  <div className="mb-1 flex items-baseline justify-between">
                    <span className={`font-display text-lg font-semibold ${side === "home" ? "text-pitch" : "text-clay"}`}>
                      {lu.team}
                    </span>
                    {lu.formation && (
                      <span className="rounded border border-line px-2 py-0.5 font-mono text-xs text-chalk">{lu.formation}</span>
                    )}
                  </div>
                  {lu.coach && <div className="mb-3 text-xs text-mist">Entraîneur : {lu.coach}</div>}
                  <div className="space-y-1">
                    {lu.xi.map((p, i) => (
                      <div key={i} className="flex items-center gap-2 border-b border-line/30 py-1 text-sm">
                        <span className="w-7 shrink-0 text-right font-mono text-xs tabular text-mist">{p.number ?? "–"}</span>
                        <span className="text-chalk">{p.name}</span>
                        {p.pos && <span className="ml-auto font-mono text-xs text-mist">{p.pos}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/clubs" className="mb-5 inline-block text-sm text-pitch hover:underline">
      ← Championnats
    </Link>
  );
}
