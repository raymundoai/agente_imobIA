import subprocess
import sys


def test_capture_worker_loads_foreign_key_targets_in_fresh_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.modules.capture import worker; "
            "from app.shared.database.base import Base; "
            "assert Base.metadata.sorted_tables",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
