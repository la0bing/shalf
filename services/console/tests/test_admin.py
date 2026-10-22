"""Custom roles, bindings, guard rails and the audit log."""


def test_permission_catalog_is_grouped_by_module(admin):
    groups = {g["module"]: g for g in admin.get("/api/admin/permissions").json()}
    assert {"features", "pipelines", "serving", "models", "training", "monitoring", "admin"} <= set(
        groups
    )
    assert groups["admin"]["permissions"][0]["global_only"] is True


def test_custom_role_lifecycle(admin, make_user, other, login):
    body = {
        "name": "feature-reviewer",
        "description": "Read + promote",
        "permissions": ["features.read", "features.promote"],
    }
    role = admin.post("/api/admin/roles", json=body).json()
    assert role["builtin"] is False

    make_user("rev@example.com", "feature-reviewer", "project:demo")
    login(other, "rev@example.com", "a-long-password-1")
    assert other.get("/api/projects/demo/features/views").status_code == 200
    assert other.post("/api/projects/demo/features/promote", json={}).status_code == 200
    assert other.get("/api/projects/demo/pipelines").status_code == 403
    assert other.get("/api/admin/roles").status_code == 403

    # Editing the role changes access immediately.
    edited = {**body, "permissions": ["features.read"]}
    assert admin.put(f"/api/admin/roles/{role['id']}", json=edited).status_code == 200
    assert other.post("/api/projects/demo/features/promote", json={}).status_code == 403

    assert admin.delete(f"/api/admin/roles/{role['id']}").status_code == 409  # still bound
    binding = next(
        b for b in admin.get("/api/admin/bindings").json() if b["role"] == "feature-reviewer"
    )
    assert admin.delete(f"/api/admin/bindings/{binding['id']}").status_code == 204
    assert admin.delete(f"/api/admin/roles/{role['id']}").status_code == 204


def test_role_validation_and_builtins(admin):
    roles = {r["name"]: r for r in admin.get("/api/admin/roles").json()}
    assert {"admin", "ml-engineer", "data-scientist", "viewer"} <= set(roles)
    builtin = roles["viewer"]
    assert (
        admin.put(
            f"/api/admin/roles/{builtin['id']}", json={"name": "viewer", "permissions": ["*"]}
        ).status_code
        == 409
    )
    assert admin.delete(f"/api/admin/roles/{builtin['id']}").status_code == 409
    assert (
        admin.post(
            "/api/admin/roles", json={"name": "x", "permissions": ["features.read"]}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/admin/roles", json={"name": "bad-perm", "permissions": ["features.fly"]}
        ).status_code
        == 422
    )
    assert (
        admin.post("/api/admin/roles", json={"name": "Upper", "permissions": ["*"]}).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/admin/roles", json={"name": "wild", "permissions": ["features.*"]}
        ).status_code
        == 201
    )


def test_bindings_validation_and_self_lockout(admin):
    bad_scope = {
        "subject_type": "user",
        "subject": "a@example.com",
        "role": "viewer",
        "scope": "project:nope",
    }
    assert admin.post("/api/admin/bindings", json=bad_scope).status_code == 422
    unknown_role = {**bad_scope, "scope": "*", "role": "ghost"}
    assert admin.post("/api/admin/bindings", json=unknown_role).status_code == 404
    ok = {**bad_scope, "scope": "*"}
    assert admin.post("/api/admin/bindings", json=ok).status_code == 201
    assert admin.post("/api/admin/bindings", json=ok).status_code == 409  # duplicate

    mine = next(
        b for b in admin.get("/api/admin/bindings").json() if b["subject"] == "admin@example.com"
    )
    assert admin.delete(f"/api/admin/bindings/{mine['id']}").status_code == 409

    me = next(u for u in admin.get("/api/admin/users").json() if u["email"] == "admin@example.com")
    assert admin.patch(f"/api/admin/users/{me['id']}", json={"disabled": True}).status_code == 409


def test_audit_log_records_changes(admin, make_user):
    make_user("aud@example.com", "viewer")
    admin.post("/api/admin/roles", json={"name": "audited", "permissions": ["models.read"]})
    actions = [e["action"] for e in admin.get("/api/admin/audit").json()]
    assert {"auth.login", "user.create", "binding.create", "role.create"} <= set(actions)
    only_roles = admin.get("/api/admin/audit?action=role.").json()
    assert {e["action"] for e in only_roles} == {"role.create"}


def test_settings_never_expose_secrets(admin):
    settings = admin.get("/api/admin/settings").json()
    assert settings["oidc"][0]["client_id"] == "console"
    assert "idp-secret" not in str(settings)
    assert settings["projects"] == [
        {"name": "demo", "backend": "local", "pipeline_runner": "thread"}
    ]
