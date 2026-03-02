import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { checkSetupRequired } from "@/api/auth";
import { fetchCurrentUser } from "@/api/users";
import type { CurrentUser } from "@/api/users";
import { ApiTransportError } from "@/lib/api-errors";

type AuthState =
  | { status: "loading" }
  | { status: "setup-required" }
  | { status: "unauthenticated" }
  | { status: "authenticated"; user: CurrentUser };

type AuthGuardProps = {
  children: (user: CurrentUser) => JSX.Element;
};

export function AuthGuard({ children }: AuthGuardProps): JSX.Element {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const setupRequired = await checkSetupRequired();
        if (cancelled) return;
        if (setupRequired) {
          setAuth({ status: "setup-required" });
          return;
        }
      } catch {
        // If setup-required check itself fails, try to proceed with auth check.
      }

      try {
        const user = await fetchCurrentUser();
        if (!cancelled) setAuth({ status: "authenticated", user });
      } catch (err) {
        if (!cancelled) {
          const is401 = err instanceof ApiTransportError && err.status === 401;
          setAuth({ status: is401 ? "unauthenticated" : "unauthenticated" });
        }
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  if (auth.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (auth.status === "setup-required") {
    return <Navigate to="/setup" replace />;
  }

  if (auth.status === "unauthenticated") {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children(auth.user);
}
