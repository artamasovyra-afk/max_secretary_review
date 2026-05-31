import {
  createContext,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useLocation } from "react-router-dom";
import { createMaxWebAppSession, getCurrentAuthSession, logoutAuthSession } from "../api/auth";
import { ApiError, setApiAuthContext } from "../api/client";
import type { AuthSession, AuthSource } from "../types/auth";
import {
  buildDevAuthSearch,
  emptyDevAuthState,
  parseDevAuthFromSearch,
  type DevAuthState,
} from "./devAuth";
import { getMaxInitData } from "./maxWebApp";

interface AuthSessionState {
  status: "loading" | "authenticated" | "unauthenticated";
  source: AuthSource;
  session: AuthSession | null;
  devAuth: DevAuthState;
  error: string | null;
}

export interface AuthContextValue extends DevAuthState {
  loading: boolean;
  authenticated: boolean;
  user: AuthSession["user"] | null;
  availableChats: AuthSession["context"]["available_chats"];
  error: string | null;
  authSource: AuthSource;
  hasAuth: boolean;
  devWarning: string | null;
  authSearch: string;
  withAuthSearch: (path: string) => string;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const location = useLocation();
  const devAuth = useMemo(
    () => (isDevAuthAllowed() ? parseDevAuthFromSearch(location.search) : emptyDevAuthState()),
    [location.search],
  );
  const [state, setState] = useState<AuthSessionState>(() => ({
    status: "loading",
    source: "none",
    session: null,
    devAuth: emptyDevAuthState(),
    error: null,
  }));

  const bootstrap = useCallback(async () => {
    if (devAuth.userId) {
      setApiAuthContext({
        userId: devAuth.userId,
        organizationId: devAuth.organizationId,
        chatId: devAuth.chatId,
        roles: devAuth.roles,
      });
      setState({
        status: "authenticated",
        source: "dev",
        session: null,
        devAuth,
        error: null,
      });
      return;
    }

    setApiAuthContext(null);
    setState((current) => ({
      ...current,
      status: "loading",
      source: "none",
      error: null,
    }));

    try {
      const session = await getCurrentAuthSession();
      setState({
        status: "authenticated",
        source: "existing_session",
        session,
        devAuth: emptyDevAuthState(),
        error: null,
      });
      return;
    } catch (requestError) {
      if (!isUnauthorized(requestError)) {
        setState({
          status: "unauthenticated",
          source: "none",
          session: null,
          devAuth: emptyDevAuthState(),
          error: "Не удалось подключиться к серверу. Проверьте соединение и попробуйте ещё раз.",
        });
        return;
      }
    }

    const initData = getMaxInitData();
    if (!initData) {
      setState({
        status: "unauthenticated",
        source: "none",
        session: null,
        devAuth: emptyDevAuthState(),
        error: null,
      });
      return;
    }

    try {
      await createMaxWebAppSession(initData);
      const session = await getCurrentAuthSession();
      setState({
        status: "authenticated",
        source: "max_webapp",
        session,
        devAuth: emptyDevAuthState(),
        error: null,
      });
    } catch (requestError) {
      setState({
        status: "unauthenticated",
        source: "none",
        session: null,
        devAuth: emptyDevAuthState(),
        error: isAuthFailure(requestError)
          ? "Не удалось подтвердить вход через MAX. Откройте WebApp заново из MAX."
          : "Не удалось подключиться к серверу. Проверьте соединение и попробуйте ещё раз.",
      });
    }
  }, [devAuth]);

  useEffect(() => {
    let active = true;
    bootstrap().finally(() => {
      if (!active) {
        return;
      }
    });
    return () => {
      active = false;
      setApiAuthContext(null);
    };
  }, [bootstrap]);

  const logout = useCallback(async () => {
    setApiAuthContext(null);
    try {
      await logoutAuthSession();
    } finally {
      setState({
        status: "unauthenticated",
        source: "none",
        session: null,
        devAuth: emptyDevAuthState(),
        error: null,
      });
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const authSearch = buildDevAuthSearch(state.devAuth);
    const user = state.session?.user ?? null;
    const context = state.session?.context ?? null;
    const userId = user?.id ?? state.devAuth.userId;
    const organizationId = context?.organization_id ?? state.devAuth.organizationId;
    const chatId = context?.chat_id ?? state.devAuth.chatId;
    const roles = user?.roles ?? state.devAuth.roles;
    const authenticated = state.status === "authenticated" && Boolean(userId);
    return {
      userId,
      organizationId,
      chatId,
      roles,
      isDevAuth: state.source === "dev",
      source: state.devAuth.source,
      loading: state.status === "loading",
      authenticated,
      user,
      availableChats: context?.available_chats ?? [],
      error: state.error,
      authSource: state.source,
      hasAuth: authenticated,
      devWarning:
        state.source === "dev"
          ? "Dev auth mode: user_id передан через URL. В production этот режим не используется."
          : null,
      authSearch,
      withAuthSearch: (path: string) => `${path}${authSearch}`,
      logout,
    };
  }, [logout, state]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function isDevAuthAllowed(): boolean {
  return import.meta.env.DEV;
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function isAuthFailure(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 404);
}
