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