"""Explicit successor-scoped Git history identity; never a global unknown fallback.

Known absence of remotes is observed from a closed isolated configuration. Shared
history roots still conflict across clones. This is registered local accounting,
not global process exclusion, network attestation or terminal cleanup.
"""
import hashlib
import os
from pathlib import Path
import re
import stat

from .core import digest, require
from .resources import git_metadata, repository_identity

PROTOCOL = 'reviewed_local_git_v1'
CONFIG_KEYS = {'core.repositoryformatversion', 'core.filemode', 'core.bare', 'core.logallrefupdates',
               'core.ignorecase', 'core.precomposeunicode', 'core.hookspath', 'user.name', 'user.email',
               'commit.gpgsign', 'remote.origin.url', 'remote.origin.fetch'}


def regular(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.getuid() and
            before.st_size <= 8192 and not before.st_mode & 0o022, 'Unsafe local Git configuration')
    raw = path.read_bytes()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')
    require(all(getattr(before, k) == getattr(path.lstat(), k) for k in fields), 'Git configuration changed')
    return {'identity': [getattr(before, k) for k in fields], 'sha256': hashlib.sha256(raw).hexdigest()}


def inspect(path, *, allow_origin=False):
    root = Path(path)
    require(root.is_absolute() and str(root.resolve(strict=True)) == str(root) and root.is_dir(),
            'Canonical local repository required')
    git = root/'.git'
    require(git.is_dir() and not git.is_symlink() and
            git_metadata(root, 'rev-parse', '--show-toplevel') == str(root) and
            git_metadata(root, 'rev-parse', '--path-format=absolute', '--git-common-dir') == str(git),
            'Local identity requires a standalone Git root, not a linked worktree or alias')
    before = [(p.stat().st_dev, p.stat().st_ino) for p in (root, git)]
    config = regular(git/'config')
    # No includes, filters, fsmonitor, helpers, URL rewrites, partial clones or
    # alternate object sources. Read this before status/history-like operations.
    entries = git_metadata(root, 'config', '--local', '--no-includes', '--null', '--list').split('\0')
    keys = [row.split('\n', 1)[0].lower() for row in entries if row]
    require(keys and all(key in CONFIG_KEYS or allow_origin and
            re.fullmatch(r'branch\.[a-z0-9_./-]{1,128}\.(remote|merge)', key) for key in keys),
            'Unsupported local Git configuration')
    require(git_metadata(root, 'rev-parse', '--is-shallow-repository') == 'false', 'Shallow history is unknown')
    for relative in ('shallow', 'info/grafts', 'objects/info/alternates', 'objects/info/http-alternates', 'commondir'):
        require(not os.path.lexists(git/relative), 'Incomplete or alternate local history is unsupported')
    require(not (git/'objects').is_symlink() and not (git/'objects/info').is_symlink(), 'Shared object aliases refused')
    worktrees = git_metadata(root, 'worktree', 'list', '--porcelain').splitlines()
    require([line for line in worktrees if line.startswith('worktree ')] == ['worktree '+str(root)],
            'Local identity excludes repositories with additional worktrees')
    remotes = git_metadata(root, 'remote').splitlines()
    remote_keys = []
    if remotes:
        require(allow_origin and remotes == ['origin'], 'Local-only review cannot conceal configured remotes')
        remote = repository_identity(root)
        require(remote['status'] == 'observed', 'Configured remote remains unknown')
        remote_keys = [key for key in remote['keys'] if key.startswith('repo-remote:')]
        require(len(remote_keys) == 1, 'Exact conventional origin required')
    else:
        require(not any(key.startswith(('remote.', 'branch.')) for key in keys),
                'Residual remote configuration is not known absence')
    refs = git_metadata(root, 'for-each-ref', '--format=%(refname)').splitlines()
    require(len(refs) <= 256 and not any(ref.startswith('refs/replace/') or
            not remotes and ref.startswith('refs/remotes/') for ref in refs),
            'Replacement or residual remote references leave identity unknown')
    # HEAD is required, but is not a permanent head pin: legitimate producer
    # commits may advance it. The exact task base is checked by its own contract.
    head = git_metadata(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    require(re.fullmatch('[0-9a-f]{40}', head) is not None, 'Committed SHA-1 local history required')
    roots = sorted(set(git_metadata(root, 'rev-list', '--max-parents=0', '--all', 'HEAD').splitlines()))
    require(1 <= len(roots) <= 64 and all(re.fullmatch('[0-9a-f]{40}', oid) for oid in roots),
            'Complete bounded local history roots required')
    require(regular(git/'config') == config and
            before == [(p.stat().st_dev, p.stat().st_ino) for p in (root, git)] and
            git_metadata(root, 'for-each-ref', '--format=%(refname)').splitlines() == refs and
            not any(os.path.lexists(git/relative) for relative in
                    ('shallow', 'info/grafts', 'objects/info/alternates', 'objects/info/http-alternates', 'commondir')) and
            sorted(set(git_metadata(root, 'rev-list', '--max-parents=0', '--all', 'HEAD').splitlines())) == roots,
            'Local repository identity changed during inspection')
    info, location = git.stat(), root.stat()
    local = 'repo-local:'+digest({'device': info.st_dev, 'inode': info.st_ino})
    return {'protocol': PROTOCOL, 'rootIdentity': [location.st_dev, location.st_ino],
            'config': config, 'remotes': 'conventional_origin' if remotes else 'observed_absent',
            'historyRoots': roots,
            'keys': sorted([local, *remote_keys, *('repo-history-root:'+oid for oid in roots)])}
