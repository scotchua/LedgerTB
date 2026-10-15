from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import folder_picker


def test_macos_folder_picker_returns_the_native_selection(monkeypatch, tmp_path):
    picked = tmp_path / "Exports"
    picked.mkdir()
    calls = []
    monkeypatch.setattr(folder_picker.sys, "platform", "darwin")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0, stdout=f"{picked}\n", stderr=""),
    )

    assert folder_picker.choose_folder(tmp_path) == str(picked.resolve())
    assert calls[0][0][0] == "/usr/bin/osascript"
    assert calls[0][0][-1] == str(tmp_path.resolve())


def test_macos_folder_picker_treats_cancel_as_no_change(monkeypatch, tmp_path):
    monkeypatch.setattr(folder_picker.sys, "platform", "darwin")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="execution error: User canceled. (-128)"
        ),
    )

    assert folder_picker.choose_folder(tmp_path) is None


def test_macos_folder_picker_treats_cancel_code_as_no_change(monkeypatch, tmp_path):
    monkeypatch.setattr(folder_picker.sys, "platform", "darwin")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="execution error: (-128)"
        ),
    )

    assert folder_picker.choose_folder(tmp_path) is None


@pytest.mark.parametrize(
    ("stderr", "message"),
    [("Finder denied access", "Finder denied access"),
     ("", "Finder could not choose a folder.")],
)
def test_macos_folder_picker_reports_failure(monkeypatch, tmp_path, stderr, message):
    monkeypatch.setattr(folder_picker.sys, "platform", "darwin")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2, stdout="", stderr=stderr
        ),
    )

    with pytest.raises(RuntimeError, match=f"^{message}$"):
        folder_picker.choose_folder(tmp_path)


def test_windows_picker_passes_initial_path_without_script_interpolation(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(folder_picker.sys, "platform", "win32")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0, stdout=str(tmp_path), stderr=""),
    )

    assert folder_picker.choose_folder(tmp_path) == str(tmp_path.resolve())
    command, kwargs = calls[0]
    assert command[:4] == ["powershell.exe", "-NoProfile", "-STA", "-Command"]
    assert str(tmp_path) not in command[-1]
    assert kwargs["env"]["LEDGERTB_FOLDER_PICKER_START"] == str(tmp_path.resolve())


@pytest.mark.parametrize(
    ("stderr", "message"),
    [("PowerShell denied access", "PowerShell denied access"),
     ("", "Windows could not choose a folder.")],
)
def test_windows_folder_picker_reports_failure(monkeypatch, tmp_path, stderr, message):
    monkeypatch.setattr(folder_picker.sys, "platform", "win32")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2, stdout="", stderr=stderr
        ),
    )

    with pytest.raises(RuntimeError, match=f"^{message}$"):
        folder_picker.choose_folder(tmp_path)


def test_windows_folder_picker_uses_zero_when_creation_flag_is_missing(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(folder_picker.sys, "platform", "win32")
    monkeypatch.delattr(folder_picker.subprocess, "CREATE_NO_WINDOW", raising=False)
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda command, **kwargs: calls.append(kwargs)
        or SimpleNamespace(returncode=0, stdout=str(tmp_path), stderr=""),
    )

    assert folder_picker.choose_folder(tmp_path) == str(tmp_path.resolve())
    assert calls[0]["creationflags"] == 0


def test_linux_without_desktop_picker_explains_manual_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(folder_picker.sys, "platform", "linux")
    monkeypatch.setattr(folder_picker.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="enter the folder path"):
        folder_picker.choose_folder(tmp_path)


def test_linux_folder_picker_returns_zenity_selection(monkeypatch, tmp_path):
    picked = tmp_path / "Exports"
    picked.mkdir()
    calls = []
    monkeypatch.setattr(folder_picker.sys, "platform", "linux")
    monkeypatch.setattr(folder_picker.shutil, "which", lambda name: "/usr/bin/zenity")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0, stdout=f"{picked}\n", stderr=""),
    )

    assert folder_picker.choose_folder(tmp_path) == str(picked.resolve())
    assert calls[0][0][0] == "/usr/bin/zenity"
    assert calls[0][0][-1] == f"--filename={tmp_path.resolve()}{folder_picker.os.sep}"


def test_linux_folder_picker_treats_cancel_as_no_change(monkeypatch, tmp_path):
    monkeypatch.setattr(folder_picker.sys, "platform", "linux")
    monkeypatch.setattr(folder_picker.shutil, "which", lambda name: "/usr/bin/zenity")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr=""
        ),
    )

    assert folder_picker.choose_folder(tmp_path) is None


@pytest.mark.parametrize(
    ("stderr", "message"),
    [("Zenity denied access", "Zenity denied access"),
     ("", "Could not choose a folder.")],
)
def test_linux_folder_picker_reports_failure(monkeypatch, tmp_path, stderr, message):
    monkeypatch.setattr(folder_picker.sys, "platform", "linux")
    monkeypatch.setattr(folder_picker.shutil, "which", lambda name: "/usr/bin/zenity")
    monkeypatch.setattr(
        folder_picker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2, stdout="", stderr=stderr
        ),
    )

    with pytest.raises(RuntimeError, match=f"^{message}$"):
        folder_picker.choose_folder(tmp_path)


def test_starting_folder_falls_back_from_a_missing_child(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert folder_picker._starting_folder(missing) == str(tmp_path.resolve())
