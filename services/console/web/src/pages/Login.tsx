import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { api, type Providers } from "../api";
import { useAuth } from "../auth";
import { Logo } from "../components/Layout";
import { ErrorAlert, Loading } from "../components/ui";
import { useAction, useApi } from "../hooks";

export function Login() {
  const { me, loading, refresh } = useAuth();
  const [params] = useSearchParams();
  const returnTo = params.get("return_to") || "/";
  const providers = useApi<Providers>("/api/auth/providers");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useAction(async () => {
    await api("/auth/login", { method: "POST", body: { email, password } });
    await refresh();
  });

  if (loading || providers.loading) return <Loading />;
  if (me) return <Navigate to={returnTo.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/"} replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void signIn.run();
  };
  const oidc = providers.data?.oidc ?? [];

  return (
    <div className="login-page">
      <div className="card login-card">
        <div className="brand" style={{ padding: 0 }}><Logo /> shalf console</div>
        <div>
          <h1>Sign in</h1>
          <p className="muted">Use your organisation account.</p>
        </div>
        <ErrorAlert error={params.get("error")} />
        {oidc.map((p) => (
          <a key={p.id} className="button primary sso-button" href={`${p.login_url}?return_to=${encodeURIComponent(returnTo)}`}>
            Continue with {p.name}
          </a>
        ))}
        {providers.data?.local && (
          <>
            {oidc.length > 0 && <div className="divider">or with a local account</div>}
            <form className="stack" onSubmit={submit}>
              <label>Email<input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
              <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
              <ErrorAlert error={signIn.error} />
              <button className={oidc.length ? "" : "primary"} type="submit" disabled={signIn.pending}>
                {signIn.pending ? "Signing in…" : "Sign in"}
              </button>
            </form>
          </>
        )}
        {!providers.data?.local && oidc.length === 0 && <ErrorAlert error="No sign-in method is configured." />}
      </div>
    </div>
  );
}
