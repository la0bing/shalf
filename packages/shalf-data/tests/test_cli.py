import json
import textwrap

from shalf.data.cli import main


def test_cli_end_to_end(tmp_path, db_path, capsys):
    (tmp_path / "shalf.yaml").write_text(
        "project: cli\ndefinitions: defs.py\nonline_store:\n  type: sqlite\n  path: online.db\n"
    )
    (tmp_path / "defs.py").write_text(
        textwrap.dedent(
            f"""
            from shalf.data import Entity, FeatureView, Field, SQLiteSource, ValueType
            customer = Entity(name="customer", join_key="customer_id")
            profiles_cli = FeatureView(
                name="profiles_cli", entities=[customer],
                source=SQLiteSource(
                    name="p", path={str(db_path)!r}, table="profiles", timestamp_field="updated_at"
                ),
                schema=[Field("tier", ValueType.STRING)],
            )
            """
        )
    )
    repo = ["--repo", str(tmp_path)]
    assert main([*repo, "apply"]) == 0
    assert main([*repo, "list", "views"]) == 0
    assert "profiles_cli" in capsys.readouterr().out

    main([*repo, "materialize", "--end", "2024-01-02T00:00:00+00:00"])
    assert json.loads(capsys.readouterr().out) == {"profiles_cli": 2}
    assert (tmp_path / "online.db").exists()

    spine = tmp_path / "spine.csv"
    spine.write_text("customer_id,event_timestamp\n1,2024-01-01T11:00:00+00:00\n")
    out = tmp_path / "train.csv"
    main(
        [
            *repo,
            "historical",
            "--entity-csv",
            str(spine),
            "--features",
            "profiles_cli:tier",
            "--out",
            str(out),
        ]
    )
    assert "gold" in out.read_text()


def test_cli_logic_change_rollout(tmp_path, db_path, capsys):
    import sys

    (tmp_path / "shalf.yaml").write_text(
        "project: rollout\ndefinitions: defs_rollout.py\n"
        "online_store: {type: sqlite, path: online.db}\n"
        "offline_store: {type: pandas, cache_path: cache}\n"
    )

    def write_defs(where: str) -> None:
        sys.modules.pop("defs_rollout", None)  # each CLI run is a fresh process in real life
        (tmp_path / "defs_rollout.py").write_text(
            textwrap.dedent(
                f"""
                from shalf.data import Entity, FeatureView, SQLiteSource
                customer = Entity(name="customer", join_key="customer_id")
                credit = FeatureView(
                    name="credit", entities=[customer], schema={{"credit": float}},
                    source=SQLiteSource(
                        name="p", path={str(db_path)!r}, timestamp_field="updated_at",
                        query="SELECT * FROM profiles {where}",
                    ),
                )
                """
            )
        )

    def run(*args: str):
        capsys.readouterr()
        assert main(["--repo", str(tmp_path), *args]) == 0
        return json.loads(capsys.readouterr().out)

    write_defs("")
    run("materialize", "--end", "2024-01-02T00:00:00+00:00")
    assert [r["status"] for r in run("plan")] == ["unchanged"]

    write_defs("WHERE tier != 'gold'")  # logic change
    assert [r["status"] for r in run("plan")] == ["changed"]
    assert run("backfill", "--end", "2024-01-02T00:00:00+00:00") == {"credit": 2}
    assert [r["status"] for r in run("plan")] == ["changed"]  # not promoted yet
    assert list(run("promote")) == ["credit"]
    assert [r["status"] for r in run("plan")] == ["unchanged"]
    assert len(list((tmp_path / "cache" / "credit").iterdir())) == 2  # both versions kept
