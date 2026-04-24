import { useQueryClient } from "@tanstack/react-query";
import { createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";

import {
  ActiveWorkspace,
  RequestScope,
  getActiveWorkspace,
  setActiveWorkspace,
  setRequestScope,
  subscribeActiveWorkspace
} from "@/lib/request-scope";

type AccessScopeContextValue = {
  scope: RequestScope;
  workspace: ActiveWorkspace;
  setScope: (scope: RequestScope) => void;
  setWorkspace: (workspace: ActiveWorkspace) => void;
};

const AccessScopeContext = createContext<AccessScopeContextValue | null>(null);

type AccessScopeProviderProps = {
  children: ReactNode;
};

export function AccessScopeProvider({ children }: AccessScopeProviderProps) {
  const [workspace, setWorkspaceState] = useState<ActiveWorkspace>(() => getActiveWorkspace());
  const queryClient = useQueryClient();
  const didMountRef = useRef(false);

  useEffect(() => subscribeActiveWorkspace(setWorkspaceState), []);

  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true;
      return;
    }
    void queryClient.invalidateQueries();
  }, [queryClient, workspace]);

  const scope: RequestScope = workspace.kind === "personal" ? "personal" : "group";

  const value = useMemo<AccessScopeContextValue>(
    () => ({
      scope,
      workspace,
      setScope: setRequestScope,
      setWorkspace: setActiveWorkspace
    }),
    [scope, workspace]
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
