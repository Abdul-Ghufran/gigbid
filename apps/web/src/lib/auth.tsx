import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, call, tokenStore, type UserOut } from "./api/client";

type Auth = { user: UserOut | null; loading: boolean; signIn: (t: string, u: UserOut) => void; signOut: () => void; refresh: () => Promise<void> };
const Ctx = createContext<Auth>({ user: null, loading: true, signIn: () => {}, signOut: () => {}, refresh: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    if (!tokenStore.get()) { setUser(null); setLoading(false); return; }
    try { setUser(await call(api.GET("/api/auth/me"))); } catch { setUser(null); }
    setLoading(false);
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return (
    <Ctx.Provider value={{
      user, loading, refresh,
      signIn: (t, u) => { tokenStore.set(t); setUser(u); },
      signOut: () => { tokenStore.set(null); setUser(null); },
    }}>{children}</Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
