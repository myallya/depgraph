import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from depgraph import parse_packages, get_direct_dependencies, parse_args
import argparse

SAMPLE = """
P:bash
V:5.2.21-r0
D:so:libc.musl-x86_64.so.1 so:libreadline.so.8 busybox

P:zlib
V:1.3.1-r0
D:so:libc.musl-x86_64.so.1
"""

def test_parse_packages():
    packages = parse_packages(SAMPLE)
    assert "bash" in packages
    assert packages["bash"] == ["so:libc.musl-x86_64.so.1", "so:libreadline.so.8", "busybox"]


def test_get_direct_dependencies():
    packages = parse_packages(SAMPLE)
    deps = get_direct_dependencies(packages, "bash")
    assert "busybox" in deps


def test_parse_args():
    args = parse_args(["-p", "bash", "-r", "https://example.com", "-m", "url"])
    assert args.package == "bash"
    assert args.mode == "url"