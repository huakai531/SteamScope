import { PlayerApp } from "@/components/player-app";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
}: {
  params: Promise<{ handle: string; appid?: string }>;
}) {
  const { handle, appid } = await params;
  return (
    <PlayerApp
      key={handle + "overview" + (appid ?? "")}
      handle={handle}
      view="overview"
      appid={appid}
    />
  );
}
