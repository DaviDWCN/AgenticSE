from pathlib import Path

from agenticse.cli import main


def test_cli_record_and_awaken_round_trip(tmp_path: Path, capsys):
    store = tmp_path / "state.json"
    assert main(["--store", str(store), "record-lesson", "Always validate cart", "--class", "CartService"]) == 0
    assert main(["--store", str(store), "record-dependency", "CheckoutService", "CartService"]) == 0

    assert main(["--store", str(store), "awaken", "Fix CheckoutService cart bug"]) == 0

    output = capsys.readouterr().out
    assert "Always validate cart" in output
    assert "CartService" in output


def test_cli_active_task_lifecycle(tmp_path: Path, capsys):
    store = tmp_path / "state.json"
    assert main(["--store", str(store), "start-task", "Fix flaky checkout", "--active-file", "tests/test_checkout.py"]) == 0
    assert main([
        "--store",
        str(store),
        "ingest",
        "--source",
        "terminal",
        "--kind",
        "stack_trace",
        "--payload",
        "AssertionError at tests/test_checkout.py:12",
    ]) == 0
    assert main(["--store", str(store), "context"]) == 0

    output = capsys.readouterr().out
    assert "AssertionError" in output

    assert main(["--store", str(store), "finish-task", "--lesson", "Checkout test requires fixture isolation"]) == 0
    assert main(["--store", str(store), "stats"]) == 0
    stats = capsys.readouterr().out
    assert "Active task: no" in stats
    assert "Vector records:" in stats


def test_cli_payload_file(tmp_path: Path, capsys):
    store = tmp_path / "state.json"
    payload = tmp_path / "payload.txt"
    payload.write_text("patch applied", encoding="utf-8")

    assert main(["--store", str(store), "start-task", "Apply patch"]) == 0
    assert main([
        "--store",
        str(store),
        "ingest",
        "--source",
        "ide",
        "--kind",
        "ast_change",
        "--payload-file",
        str(payload),
    ]) == 0
    assert main(["--store", str(store), "context"]) == 0

    assert "patch applied" in capsys.readouterr().out


def test_cli_respects_agenticse_store_env_var(tmp_path: Path, monkeypatch):
    store = tmp_path / "env-state.json"
    monkeypatch.setenv("AGENTICSE_STORE", str(store))

    assert main(["record-lesson", "Environment store works"]) == 0

    assert store.exists()


def test_cli_store_flag_overrides_env_var(tmp_path: Path, monkeypatch):
    env_store = tmp_path / "env-state.json"
    flag_store = tmp_path / "flag-state.json"
    monkeypatch.setenv("AGENTICSE_STORE", str(env_store))

    assert main(["--store", str(flag_store), "record-lesson", "Flag store wins"]) == 0

    assert flag_store.exists()
    assert not env_store.exists()


def test_cli_context_without_active_task_is_friendly(tmp_path: Path, capsys):
    store = tmp_path / "state.json"

    assert main(["--store", str(store), "context"]) == 0

    assert "No active task." in capsys.readouterr().out


def test_cli_stats_reports_store_observability(tmp_path: Path, capsys):
    store = tmp_path / "state.json"
    assert main(["--store", str(store), "record-lesson", "Stats are useful"]) == 0

    assert main(["--store", str(store), "stats"]) == 0

    output = capsys.readouterr().out
    assert f"Store path: {store}" in output
    assert "Snapshot size:" in output
    assert "Backup available:" in output


def test_cli_rejects_oversized_payload(tmp_path: Path, capsys):
    store = tmp_path / "state.json"
    assert main(["--store", str(store), "start-task", "Payload limit"]) == 0

    code = main([
        "--store",
        str(store),
        "ingest",
        "--source",
        "terminal",
        "--payload",
        "too big",
        "--max-payload-bytes",
        "3",
    ])

    assert code == 1
    assert "limit is 3 bytes" in capsys.readouterr().err


def test_cli_restore_backup_for_corrupted_primary(tmp_path: Path, capsys):
    store = tmp_path / "state.json"
    assert main(["--store", str(store), "record-lesson", "First good state"]) == 0
    assert main(["--store", str(store), "record-lesson", "Second good state"]) == 0
    store.write_text("{not json", encoding="utf-8")

    assert main(["--store", str(store), "--restore-backup", "awaken", "First good state"]) == 0

    assert "First good state" in capsys.readouterr().out