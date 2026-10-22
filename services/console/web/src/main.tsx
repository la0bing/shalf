import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth";
import { Forbidden, RequireAuth, RequireProject } from "./components/guards";
import { Layout } from "./components/Layout";
import { Access } from "./pages/admin/Access";
import { Audit } from "./pages/admin/Audit";
import { Roles } from "./pages/admin/Roles";
import { Settings } from "./pages/admin/Settings";
import { Users } from "./pages/admin/Users";
import { FeatureDetail } from "./pages/FeatureDetail";
import { Features } from "./pages/Features";
import { Login } from "./pages/Login";
import { Models } from "./pages/Models";
import { Overview } from "./pages/Overview";
import { Pipelines } from "./pages/Pipelines";
import { Planned } from "./pages/Planned";
import { Serving } from "./pages/Serving";
import "./styles.css";

function Global({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth();
  return can(permission, "*") ? <>{children}</> : <Forbidden permission={permission} />;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Overview />} />
        <Route path="features" element={<RequireProject permission="features.read"><Features /></RequireProject>} />
        <Route path="features/:view" element={<RequireProject permission="features.read"><FeatureDetail /></RequireProject>} />
        <Route path="pipelines" element={<RequireProject permission="pipelines.read"><Pipelines /></RequireProject>} />
        <Route path="serving" element={<RequireProject permission="serving.read"><Serving /></RequireProject>} />
        <Route path="models" element={<Global permission="models.read"><Models /></Global>} />
        <Route path="training" element={<Planned moduleKey="training" />} />
        <Route path="monitoring" element={<Planned moduleKey="monitoring" />} />
        <Route path="admin/users" element={<Global permission="admin.users.read"><Users /></Global>} />
        <Route path="admin/roles" element={<Global permission="admin.roles.manage"><Roles /></Global>} />
        <Route path="admin/access" element={<Global permission="admin.bindings.manage"><Access /></Global>} />
        <Route path="admin/audit" element={<Global permission="admin.audit.read"><Audit /></Global>} />
        <Route path="admin/settings" element={<Global permission="admin.settings.read"><Settings /></Global>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
