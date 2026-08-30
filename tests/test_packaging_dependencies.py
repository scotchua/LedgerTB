import ast
import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = ("requirements-macos-arm64.lock", "requirements-windows.lock")
LOCK_PLATFORMS = {
    "requirements-macos-arm64.lock": "darwin",
    "requirements-windows.lock": "win32",
}


def _direct_requirements(path, sys_platform):
    requirements = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            requirement = Requirement(line)
            if requirement.marker is None or requirement.marker.evaluate(
                {"sys_platform": sys_platform}
            ):
                requirements.add(canonicalize_name(requirement.name))
    return requirements


def _locked_requirements(path):
    requirements = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==", line.strip())
        if match:
            requirements.add(canonicalize_name(match.group(1)))
    return requirements


def _assert_direct_requirements_are_locked(requirements_path, lock_path, sys_platform):
    missing = (
        _direct_requirements(requirements_path, sys_platform)
        - _locked_requirements(lock_path)
    )
    assert not missing, f"{lock_path.name} is missing direct requirements: {sorted(missing)}"


@pytest.mark.parametrize("lock_name", LOCK_FILES)
def test_every_direct_requirement_is_in_each_platform_lock(lock_name):
    _assert_direct_requirements_are_locked(
        ROOT / "requirements.txt", ROOT / lock_name, LOCK_PLATFORMS[lock_name],
    )


def test_lock_drift_check_rejects_a_missing_direct_requirement(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("alpha>=1\nbeta>=2; python_version >= '3.12'\n", encoding="utf-8")
    lock = tmp_path / "requirements.lock"
    lock.write_text("alpha==1.0\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="beta"):
        _assert_direct_requirements_are_locked(requirements, lock, "win32")


def test_selfcheck_lists_new_runtime_modules():
    tree = ast.parse((ROOT / "run_ledgertb.py").read_text(encoding="utf-8"))
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SELFCHECK_MODULES"
                for target in node.targets)
    )
    modules = set(ast.literal_eval(assignment.value))
    expected = {
        "rapidfuzz", "httpx",
        "services.coa_import", "services.bank_feed", "services.ar_ap",
        "services.inventory", "services.payroll_recording", "services.fixed_assets",
        "services.ai_providers", "services.ai_providers.anthropic_format",
        "services.ai_providers.openai_format", "models.payables",
        "models.receivables", "models.payroll", "models.fixed_asset",
    }

    assert expected <= modules
