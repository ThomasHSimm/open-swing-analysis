from open_swing_analysis import __version__
from open_swing_analysis.cli import main


def test_version_is_pose_v01_development_release() -> None:
    assert __version__ == "0.1.0a3"


def test_status_distinguishes_contracts_from_analysis(capsys) -> None:
    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "video ingestion are implemented" in output
    assert "MediaPipe pose extraction is implemented" in output
    assert "swing analysis are not implemented" in output
