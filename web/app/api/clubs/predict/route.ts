import { NextRequest, NextResponse } from "next/server";
import { clubModel } from "@/lib/api";

// Proxy même origine → FastAPI (comme /api/predict, version club).
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const league = Number(searchParams.get("league"));
  const home = searchParams.get("home");
  const away = searchParams.get("away");

  if (!league || !home || !away) {
    return NextResponse.json(
      { error: "Paramètres 'league', 'home' et 'away' requis." },
      { status: 400 }
    );
  }

  try {
    const prediction = await clubModel.predict(league, home, away);
    return NextResponse.json(prediction);
  } catch (e) {
    return NextResponse.json(
      { error: `Ligue non entraînée ou équipe inconnue : ${home} / ${away}.` },
      { status: 404 }
    );
  }
}
