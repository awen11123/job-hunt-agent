from pathlib import Path

INSTALLER_SCRIPT = Path("packaging/installer.iss")
BUILD_SCRIPT = Path("scripts/build_windows_installer.ps1")


def test_installer_creates_shortcuts_and_keeps_data_on_uninstall() -> None:
    script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert "{autoprograms}" in script
    assert "{autodesktop}" in script
    assert "JobHuntAgent.exe" in script
    assert "%APPDATA%" not in script
    assert "UninstallDelete" not in script


def test_installer_is_per_user_and_does_not_require_elevation() -> None:
    script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert "DefaultDirName={localappdata}\\Programs\\JobHuntAgent" in script
    assert "PrivilegesRequired=lowest" in script
    assert "{commonprograms}" not in script
    assert "{commondesktop}" not in script


def test_installer_uses_injected_semantic_version_and_stable_output_name() -> None:
    script = INSTALLER_SCRIPT.read_text(encoding="utf-8")
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "{#MyAppVersion}" in script
    assert "OutputBaseFilename=JobHuntAgent-Setup-{#MyAppVersion}" in script
    assert "/DMyAppVersion=$Version" in build
    assert "^\\d+\\.\\d+\\.\\d+" in build


def test_build_script_validates_packaged_application_before_compiling() -> None:
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "dist\\JobHuntAgent\\JobHuntAgent.exe" in build
    assert "_internal\\web_static\\index.html" in build
    assert "ISCC.exe" in build
    assert "$env:LOCALAPPDATA" in build
    assert "dist\\installer\\JobHuntAgent-Setup-$Version.exe" in build
    assert "C:\\Users\\" not in build


def test_build_script_runs_artifact_verifier_before_compiler() -> None:
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    verifier_position = build.index("verify_release_artifact.py")
    compiler_position = build.index("& $compiler")

    assert verifier_position < compiler_position
    assert "$LASTEXITCODE" in build[verifier_position:compiler_position]
