import pytest

from shalf_console.modules import default_modules
from shalf_console.rbac import (
    GLOBAL_SCOPE,
    PermissionCatalog,
    Principal,
    effective_permissions,
    expand,
)
from shalf_console.rbac.evaluator import Grant


@pytest.fixture()
def catalog():
    catalog = PermissionCatalog()
    for module in default_modules():
        catalog.add(*module.permissions)
    return catalog


def test_wildcards_expand_against_the_catalog(catalog):
    assert expand(["features.*"], catalog) == {
        "features.read", "features.preview", "features.backfill", "features.promote"
    }  # fmt: skip
    assert "admin.roles.manage" in expand(["*"], catalog)
    with pytest.raises(ValueError, match="Unknown permissions"):
        catalog.validate_patterns(["features.read", "nope.*", "features.delete"])


def test_user_group_and_project_scoping(catalog):
    grants = [
        Grant("user", "ana@x.com", GLOBAL_SCOPE, ["features.read"]),
        Grant("group", "ML-Team", "project:fraud", ["features.*", "admin.*"]),
        Grant("user", "bob@x.com", GLOBAL_SCOPE, ["*"]),
    ]
    ana = Principal("Ana@X.com", groups=("ml-team",))
    perms = effective_permissions(ana, grants, catalog, ["fraud", "churn"])
    assert perms[GLOBAL_SCOPE] == {"features.read"}
    assert perms["churn"] == {"features.read"}
    assert "features.promote" in perms["fraud"]
    assert not any(p.startswith("admin.") for p in perms["fraud"])  # admin never project-scoped

    nobody = effective_permissions(Principal("eve@x.com"), grants, catalog, ["fraud"])
    assert nobody == {GLOBAL_SCOPE: set(), "fraud": set()}
