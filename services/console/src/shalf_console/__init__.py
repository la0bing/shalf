"""shalf console: the platform's web UI and control-plane API.

* Authentication: OIDC single sign-on (any number of providers) and optional
  local accounts.
* Authorisation: role-based. Modules declare permissions, admins compose them
  into custom roles and bind roles to users or SSO groups, globally or per
  project. Every change is audited.
* Modules: features, pipelines, serving, models, training, monitoring - each
  registers its API routes, permissions and status, and the UI builds its
  navigation from that.
"""
