from open_swing_analysis import __version__
from open_swing_analysis.cli import main


def test_version_is_scaffold_version() -> None:
    assert __version__ == "0.0.0"


def test_status_is_explicit_about_implementation(capsys) -> None:
    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "V0.1 analysis pipeline is not implemented" in output
