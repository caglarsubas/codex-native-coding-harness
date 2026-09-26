"""Compatibility for the signed desktop bundle's CLI relocation.

Only a missing, explicitly configured legacy path can select the new layout.
No PATH search, download, global setting or native action is involved.
"""
from pathlib import Path
import subprocess
import sys
import re


def resolve_cli(path):
    configured = Path(path)
    if configured.exists() or sys.platform != 'darwin':
        return configured
    suffix = '/Contents/Resources/codex'
    if not str(configured).endswith(suffix):
        return configured
    bundle = Path(str(configured)[:-len(suffix)])
    if bundle.parent != Path('/Applications') or bundle.name not in ('ChatGPT.app', 'Codex.app'):
        return configured
    candidate = bundle / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
    try:
        if not candidate.is_file() or candidate.resolve(strict=True) != candidate:
            return configured
        check = subprocess.run(['/usr/bin/codesign', '--verify', '--strict',
            '-R=anchor apple generic and certificate leaf[subject.OU] = "2DC432GLL2" and identifier "codex"',
            str(candidate)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False)
        return candidate if check.returncode == 0 else configured
    except (OSError, subprocess.TimeoutExpired):
        return configured


def desktop_bundle(cli):
    """An exact installed desktop bundle, never a browser-selected executable."""
    path = Path(cli)
    for name in ('ChatGPT.app', 'Codex.app'):
        bundle = Path('/Applications') / name
        if path in (bundle / 'Contents/Resources/codex',
                    bundle / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'):
            if sys.platform == 'darwin':
                return bundle
    raise ValueError('Desktop wake requires the installed macOS Codex bundle CLI')


def open_desktop_brain(cli, brain_id):
    """Load the queued task through the official deep link; send no message."""
    if not isinstance(brain_id, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', brain_id):
        return False
    try:
        bundle = desktop_bundle(cli)
        if not bundle.is_dir() or bundle.resolve(strict=True) != bundle:
            return False
        verified = subprocess.run(['/usr/bin/codesign', '--verify', '--strict',
            '-R=anchor apple generic and certificate leaf[subject.OU] = "2DC432GLL2" and identifier "com.openai.codex"',
            str(bundle)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False)
        if verified.returncode != 0:
            return False
        opened = subprocess.run(['/usr/bin/open', '-g', '-a', str(bundle), 'codex://threads/' + brain_id],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5, check=False)
        return opened.returncode == 0
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return False
