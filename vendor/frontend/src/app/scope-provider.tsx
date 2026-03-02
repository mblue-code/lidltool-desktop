import { useQueryClient } from "@tanstack/react-query";
import { createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  RequestScope,
  getRequestScope,
  setRequestScope,
  subscribeRequestScope
} from "@/lib/request-scope";

type AccessScopeContextValue = {
  scope: RequestScope;
  setScope: (scope: RequestScope) => void;
};

const AccessScopeContext = createContext<AccessScopeContextValue | null>(null);

type AccessScopeProviderProps = {
  children: ReactNode;
};

export function AccessScopeProvider({ children }: AccessScopeProviderProps): JSX.Element {
  const [scope, setScopeState] = useState<RequestScope>(() => getRequestScope());
  const queryClient = useQueryClient();
  const didMountRef = useRef(false);

  useEffect(() => subscribeRequestScope(setScopeState), []);

  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true;
      return;
    }
    void queryClient.invalidateQueries();
  }, [scope, queryClient]);

  const value = useMemo<AccessScopeContextValue>(
    () => ({
      scope,
      setScope: setRequestScope
    }),
    [scope]
  );

  return <AccessScopeContext.Provider value={value}>{children}</AccessScopeContext.Provider>;
}

export function useAccessScope(): AccessScopeContextValue {
  const context = useContext(AccessScopeContext);
  if (!context) {
    throw new Error("useAccessScope must be used within AccessScopeProvider");
  }
  return context;
}
