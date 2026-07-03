import { api } from "@/lib/api";
import { Predictor } from "@/components/Predictor";

export const dynamic = "force-dynamic";

export default async function PredictPage() {
  const teams = await api.teams();
  return (
    <div>
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-pitch">
          Simulateur
        </p>
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
          Prédire un match
        </h1>
        <p className="mt-2 max-w-2xl text-mist">
          Choisis deux équipes. Le modèle Dixon-Coles estime les buts attendus, les
          probabilités de résultat et la distribution complète des scores.
        </p>
      </header>
      <Predictor teams={teams} />
    </div>
  );
}
