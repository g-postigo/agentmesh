"""Guards on the packaging surface, not on behaviour."""

from pathlib import Path

import chatmesh


def test_all_names_resolve():
    for name in chatmesh.__all__:
        assert hasattr(chatmesh, name), f"{name} is in __all__ but not exported"


def test_old_error_name_still_works():
    from chatmesh.errors import AgentmeshError, ChatmeshError

    assert AgentmeshError is ChatmeshError


def test_py_typed_ships():
    marker = Path(chatmesh.__file__).parent / "py.typed"
    assert marker.exists(), "py.typed is missing, type checkers will ignore the package"


def test_runnable_as_a_module():
    """`python -m chatmesh` should work, not just the console script."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "chatmesh", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "bootstrap" in out.stdout
