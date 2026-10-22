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
