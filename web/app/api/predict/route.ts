import { NextRequest, NextResponse } from "next/server";
import { api } from "@/lib/api";

// Proxy : le navigateur appelle /api/predict (même origine), Next.js relaie
// vers FastAPI en interne. Évite CORS et n'expose pas l'API publiquement.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const home = searchParams.get("home");
  const away = searchParams.get("away");
  const neutral = searchParams.get("neutral") !== "false";

  if (!home || !away) {
    return NextResponse.json(
      { error: "Paramètres 'home' et 'away' requis." },
      { status: 400 }
    );
  }

  try {
    const prediction = await api.predict(home, away, neutral);
    return NextResponse.json(prediction);
  } catch (e) {
    return NextResponse.json(
      { error: `Équipe(s) inconnue(s) du modèle : ${home} ou ${away}.` },
      { status: 404 }
    );
  }
}
