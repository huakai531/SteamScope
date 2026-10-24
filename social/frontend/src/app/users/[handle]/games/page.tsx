import { PlayerApp } from "@/components/player-app";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ handle: string; appid?: string }>;
  searchParams: Promise<{ achievements?: string }>;
}) {
  const { handle, appid } = await params;
  const achievementLibrary = (await searchParams).achievements === "true";
  return (
    <PlayerApp
      key={handle + "games" + (appid ?? "") + String(achievementLibrary)}
      handle={handle}
      view="games"
      appid={appid}
      achievementLibrary={achievementLibrary}
    />
  );
}
