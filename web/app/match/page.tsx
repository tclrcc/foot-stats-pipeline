import { api } from "@/lib/api";
import { MatchAnalysis } from "@/components/MatchAnalysis";

export const dynamic = "force-dynamic";

export default async function MatchPage() {
  const teams = await api.teams();
  return (
    <div>
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">Avant-match</p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">Dossier de match</h1>
        <p className="mt-2 max-w-2xl text-mist">
          Tout ce qu&apos;il faut pour analyser une affiche : forme, face-à-face, rapport de force,
          hommes clés, prédiction et angles à exploiter. Pensé comme un brief d&apos;avant-match.
        </p>
      </header>
      <MatchAnalysis teams={teams} />
    </div>
  );
}
