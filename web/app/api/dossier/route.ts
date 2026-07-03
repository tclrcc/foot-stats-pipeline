import { NextRequest, NextResponse } from "next/server";
import { api } from "@/lib/api";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const home = searchParams.get("home");
  const away = searchParams.get("away");
  const neutral = searchParams.get("neutral") !== "false";
  const date = searchParams.get("date") || undefined;

  if (!home || !away) {
    return NextResponse.json({ error: "Paramètres 'home' et 'away' requis." }, { status: 400 });
  }
  try {
    const dossier = await api.dossier(home, away, neutral, date);
    return NextResponse.json(dossier);
  } catch {
    return NextResponse.json(
      { error: `Équipe(s) inconnue(s) du modèle : ${home} ou ${away}.` },
      { status: 404 }
    );
  }
}
