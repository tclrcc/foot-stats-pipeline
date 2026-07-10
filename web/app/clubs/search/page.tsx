/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { players } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PlayerSearchPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = (searchParams.q ?? "").trim();
  const results = q.length >= 3 ? await players.search(q).catch(() => []) : [];

  return (
    <div>
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">Joueurs</p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">Rechercher un joueur</h1>
        <p className="mt-2 max-w-2xl text-mist">
          Tape un nom (3 caractères minimum) puis ouvre la fiche complète : profil, stats par
          compétition, parcours, palmarès et analyse approfondie.
        </p>
      </header>

      <form action="/clubs/search" method="GET" className="mb-8 flex max-w-xl gap-2">
        <input
          type="text"
          name="q"
          defaultValue={q}
          placeholder="Ex. : Mbappé, Saïd, Greenwood…"
          className="flex-1 rounded-md border border-line bg-ink px-4 py-2.5 text-chalk outline-none placeholder:text-mist/60 focus:border-pitch"
        />
        <button
          type="submit"
          className="rounded-md bg-pitch px-5 py-2.5 text-sm font-semibold text-ink transition-opacity hover:opacity-90"
        >
          Rechercher
        </button>
      </form>

      {q && q.length < 3 && (
        <p className="text-sm text-mist">Trois caractères minimum.</p>
      )}

      {q.length >= 3 && results.length === 0 && (
        <div className="rounded-card border border-line bg-slate p-8 text-center text-mist">
          Aucun joueur trouvé pour « {q} ».
        </div>
      )}

      {results.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((p) => (
            <Link
              key={p.player_id}
              href={`/clubs/player/${p.player_id}`}
              className="flex items-center gap-4 rounded-card border border-line bg-slate p-4 transition-colors hover:border-pitch"
            >
              {p.photo ? (
                <img src={p.photo} alt="" className="h-14 w-14 shrink-0 rounded-full border border-line object-cover" />
              ) : (
                <div className="grid h-14 w-14 shrink-0 place-items-center rounded-full border border-line text-mist">?</div>
              )}
              <div className="min-w-0">
                <div className="truncate font-medium text-chalk">
                  {p.firstname && p.lastname ? `${p.firstname} ${p.lastname}` : p.name}
                </div>
                <div className="mt-0.5 truncate text-xs text-mist">
                  {[p.nationality, p.age != null ? `${p.age} ans` : null, p.position]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </div>
              <span className="ml-auto shrink-0 text-xs text-pitch">Fiche →</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
