import plistlib
import re
import tomllib
from pathlib import Path

from xong import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_python_and_ios():
    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project_version = tomllib.load(project_file)["project"]["version"]
    with (ROOT / "clients/ios/Info.plist").open("rb") as plist_file:
        ios_version = plistlib.load(plist_file)["CFBundleShortVersionString"]
    xcode_project = (ROOT / "clients/ios/Xong.xcodeproj/project.pbxproj").read_text()
    marketing_versions = set(
        re.findall(r"MARKETING_VERSION = ([^;]+);", xcode_project)
    )

    assert __version__ == project_version
    assert ios_version == "$(MARKETING_VERSION)"
    assert marketing_versions == {project_version}
