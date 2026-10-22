import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, type Me, type Module, type Project } from "./api";

interface AuthState {
  me: Me | null;
  modules: Module[];
  projects: Project[];
  loading: boolean;
  project: string | null;
  setProject: (name: string) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  /** Does the user hold `permission` in `scope` ("*" = global; default: current project)? */
  can: (permission: string, scope?: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);
const PROJECT_KEY = "shalf.project";

function storedProject(): string | null {
  try {
    return window.localStorage.getItem(PROJECT_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [project, setProjectState] = useState<string | null>(storedProject());

  const refresh = useCallback(async () => {
    try {
      const [meData, moduleData, projectData] = await Promise.all([
        api<Me>("/api/me"),
        api<Module[]>("/api/modules"),
        api<Project[]>("/api/projects"),
      ]);
      setMe(meData);
      setModules(moduleData);
      setProjects(projectData);
      setProjectState((current) =>
        current && projectData.some((p) => p.name === current) ? current : (projectData[0]?.name ?? null),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setMe(null);
      else throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setProject = useCallback((name: string) => {
    setProjectState(name);
    try {
      window.localStorage.setItem(PROJECT_KEY, name);
    } catch {
      /* storage unavailable: selection lasts for this page only */
    }
  }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setMe(null);
  }, []);

  const can = useCallback(
    (permission: string, scope?: string) => {
      const key = scope ?? project ?? "*";
      return Boolean(me?.permissions[key]?.includes(permission));
    },
    [me, project],
  );

  const value = useMemo(
    () => ({ me, modules, projects, loading, project, setProject, refresh, logout, can }),
    [me, modules, projects, loading, project, setProject, refresh, logout, can],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}
