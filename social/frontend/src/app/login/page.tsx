import { Suspense } from "react";
import { LoginState } from "@/components/login-state";
export const dynamic = "force-dynamic";
export default function Page() {
  return (
    <Suspense fallback={<p role="status">Loading sign-in…</p>}>
      <LoginState />
    </Suspense>
  );
}
