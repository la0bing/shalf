from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shalf.core import load_yaml


class OIDCProvider(BaseModel):
    """An OpenID Connect identity provider (Okta, Entra ID, Google, Keycloak, Dex...).

    SAML or LDAP directories can be used through an OIDC bridge such as Dex
    or Keycloak.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    issuer: str
    client_id: str
    client_secret: str = ""
    scopes: list[str] = ["openid", "email", "profile"]
    groups_claim: str = "groups"
    email_claim: str = "email"
    name_claim: str = "name"
    allowed_domains: list[str] = []  # empty: any domain the IdP vouches for


class ProjectConfig(BaseModel):
    """A shalf project the console manages.

    ``local``: loaded in-process from ``path`` (dev, or a console image built
    FROM the project's jobs image). ``remote``: reached through the project's
    feature servers (admin API) in Kubernetes.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["local", "remote"] = "local"
    description: str = ""
    path: str | None = None
    profile: str | None = None
    serving_url: str | None = None
    eda_url: str | None = None
    admin_token: str = ""
    pipeline_runner: dict[str, Any] = {"type": "thread"}


class ConsoleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://localhost:8090"
    database_url: str = "sqlite:///console.db"
    session_ttl_hours: float = 12
    cookie_secure: bool = True
    local_login: bool = True
    bootstrap_admins: list[str] = []
    bootstrap_admin_password: str = ""
    oidc: list[OIDCProvider] = []
    projects: list[ProjectConfig] = []
    model_registry: dict[str, Any] = {"type": "local", "root": "model_registry"}
    static_dir: str | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> ConsoleSettings:
        path = path or os.environ.get("SHALF_CONSOLE_CONFIG")
        if not path:
            return cls()
        settings = cls.model_validate(load_yaml(path))
        return settings.resolve_paths(Path(path).resolve().parent)

    def resolve_paths(self, base: Path) -> ConsoleSettings:
        def fix(value: str | None) -> str | None:
            if value and not Path(value).is_absolute() and "://" not in value:
                return str(base / value)
            return value

        db = self.database_url
        if db.startswith("sqlite:///") and not db.startswith("sqlite:////"):
            db = "sqlite:///" + str(base / db.removeprefix("sqlite:///"))
        registry = dict(self.model_registry)
        if "root" in registry:
            registry["root"] = fix(registry["root"])
        return self.model_copy(
            update={
                "database_url": db,
                "projects": [p.model_copy(update={"path": fix(p.path)}) for p in self.projects],
                "model_registry": registry,
                "static_dir": fix(self.static_dir),
            }
        )
