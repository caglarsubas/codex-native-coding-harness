"""Explicit launch-only public host, never a vendor desktop bridge or dispatcher.

Only one owner-reviewed foreground exec, with a clean environment and private
empty home. No restart, background supervisor, RPC, load, binding or run control.
"""
import argparse
import os
from pathlib import Path
import platform
import pwd
import stat
import sys
import time

from .core import Refusal, digest, canonical, require
from .host_lifecycle import private_file, sync_directory, write_record
from .host_runtime import safe_path, file_record
from .native_read_client import decode
from .public_host_runtime import PROFILE, validate_pin, inspect_package, closed_entries

CONFIG = '''sandbox_mode = "workspace-write"
approval_policy = "on-request"
approvals_reviewer = "user"
cli_auth_credentials_store = "file"
allow_login_shell = false
[shell_environment_policy]
inherit = "none"
[shell_environment_policy.set]
PATH = "/usr/bin:/bin"
LANG = "C"
[sandbox_workspace_write]
network_access = false
[features]
code_mode = false
code_mode_only = false
apps = false
plugins = false
hooks = false
skip_host_skill_discovery = true
[analytics]
enabled = false
'''
FIELDS = {"schemaVersion", "profile", "runtimePackage", "cwd", "cwdIdentity", "codexHome", "homeIdentity",
          "configPin", "socketDirectory", "socketDirectoryIdentity", "nativePolicy", "credentialMode"}
POLICY = {"sandbox":"workspace-write", "approvalPolicy":"on-request", "approvalsReviewer":"user", "codeMode":False}


def directory_identity(path):
    info = safe_path(Path(path), directory=True)
    return {"device":info.st_dev,"inode":info.st_ino,"owner":info.st_uid,"mode":stat.S_IMODE(info.st_mode)}


def isolated_directory(path):
    value = Path(path); info = safe_path(value, directory=True)
    require(info.st_uid == os.getuid() and not info.st_mode & 0o077, "Canonical owner-private isolation directory required")
    return value


def setup_scope(package, cwd, codex_home, socket_directory):
    """Non-executing closed setup pin; creates/copies/configures nothing."""
    package = inspect_package(package)
    cwd = Path(cwd); safe_path(cwd, directory=True)
    home, sockets = isolated_directory(codex_home), isolated_directory(socket_directory)
    require(not home.is_relative_to(Path('/private/var/tmp')), "Codex helper home must be outside the fixed system temporary root")
    runtime = Path(package["root"])
    roots = [runtime,cwd,home,sockets]
    require(len(set(roots)) == 4 and all(not a.is_relative_to(b) for a in roots for b in roots if a != b),
            "Runtime, checkout, home and socket directories must be disjoint")
    require(home != (Path(pwd.getpwuid(os.getuid()).pw_dir)/'.codex').resolve(), "Shared Codex home is not an isolated public host")
    closed_entries(home, {'config.toml'}); closed_entries(sockets, set())
    require((cwd/'.git').is_dir() and not (cwd/'.git').is_symlink(), "An existing non-worktree Git checkout root is required")
    private_file(home/'config.toml')
    require((home/'config.toml').read_bytes() == CONFIG.encode(), "Only the fixed restricted no-plugin configuration is supported")
    # Do not silently discard managed policy or checkout config. This initial
    # profile refuses extra config layers instead of weakening their controls.
    for candidate in (cwd/'config.toml', cwd/'.codex/config.toml', Path('/etc/codex/config.toml'),
                      Path('/etc/codex/requirements.toml'), Path('/etc/codex/managed_config.toml'),
                      Path('/Library/Preferences/com.openai.codex.plist')):
        require(not candidate.exists() and not candidate.is_symlink(), "Additional configuration requires a separate qualified profile")
    socket = sockets/'host.sock'
    require(len(os.fsencode(str(socket))) <= 100, "Bounded local Unix socket path required")
    return {"schemaVersion":1,"profile":PROFILE,"runtimePackage":package,"cwd":str(cwd),
            "cwdIdentity":directory_identity(cwd), "codexHome":str(home),"homeIdentity":directory_identity(home),
            "configPin":file_record(home,'config.toml',65536),"socketDirectory":str(sockets),
            "socketDirectoryIdentity":directory_identity(sockets),"nativePolicy":POLICY.copy(),"credentialMode":"unconfigured"}


def validate_spec(value):
    require(isinstance(value,dict) and set(value) == FIELDS and type(value['schemaVersion']) is int and
            value['schemaVersion'] == 1 and value['profile'] == PROFILE and value['nativePolicy'] == POLICY and
            type(value['nativePolicy'].get('codeMode')) is bool and value['credentialMode'] == 'unconfigured',
            "Exact public launch-only manifest required; vendor reviews are not interchangeable")
    validate_pin(value['runtimePackage'])
    expected = setup_scope(value['runtimePackage']['root'],value['cwd'],value['codexHome'],value['socketDirectory'])
    require(expected == value, "Reviewed public setup changed")
    return value


def specification(path):
    return validate_spec(decode(private_file(path).read_bytes()))


def review_hash(spec):
    return digest({'profile':PROFILE,'mode':'exec','manifestHash':digest(spec)})


def environment(spec):
    # No inherited pipe, model secret, proxy, preload, plugin or DYLD variables.
    # HOME remains the real user's home; CODEX_HOME alone selects isolated state.
    user = pwd.getpwuid(os.getuid())
    return {'HOME':user.pw_dir,'USER':user.pw_name,'LOGNAME':user.pw_name,'PATH':'/usr/bin:/bin',
            'CODEX_HOME':spec['codexHome'],'TMPDIR':'/private/var/tmp'}


def exec_host(manifest, attempt, confirm_hash):
    spec = specification(manifest)
    require(sys.platform == 'darwin' and platform.machine() == 'arm64', "This public profile supports macOS ARM64 only")
    require(confirm_hash == review_hash(spec), "Exact separately reviewed public exec hash required")
    attempt = Path(attempt)
    require(attempt.is_absolute() and attempt.parent.resolve(strict=True) == attempt.parent, "Canonical new private attempt required")
    isolated_directory(attempt.parent)
    # Creating the journal inside a pinned directory would change its review.
    require(all(not attempt.is_relative_to(Path(spec[key])) for key in ('cwd','codexHome','socketDirectory')) and
            not attempt.is_relative_to(Path(spec['runtimePackage']['root'])), "Launch journal must be outside reviewed scope")
    try: attempt.mkdir(mode=0o700)
    except FileExistsError: raise Refusal("Public launch already has an intent; inspect it, never relaunch") from None
    sync_directory(attempt.parent)
    write_record(attempt/'launch.json', {'spec':spec,'manifestHash':digest(spec),'reviewHash':confirm_hash,
                                       'mode':'exec','createdAt':time.time()})
    fd = os.open(attempt/'exec.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream: stream.flush(); os.fsync(stream.fileno())
    sync_directory(attempt)
    # Claim precedes final package/config checks and any process boundary.
    # Drift, interrupted persistence and exec failure permanently consume intent.
    validate_spec(spec)
    write_record(attempt/'status.json', {'status':'exec_boundary_issued','mode':'exec','profile':PROFILE,
                 'pid':os.getpid(),'parentPid':os.getppid(),'observedAt':time.time(),
                 'hostReady':False,'nativeToolsQualified':False,'bindingInstalled':False,
                 'terminalSafety':'unknown','restarted':False})
    binary = str(Path(spec['runtimePackage']['root'])/'bin/codex')
    argv = [binary,'app-server','--listen','unix://'+str(Path(spec['socketDirectory'])/'host.sock')]
    try:
        os.chdir(spec['cwd'])
        with open(os.devnull,'rb') as quiet_input, open(os.devnull,'wb') as quiet_output:
            os.dup2(quiet_input.fileno(),0); os.dup2(quiet_output.fileno(),1); os.dup2(quiet_output.fileno(),2)
        os.execve(binary,argv,environment(spec))
        raise OSError('Exec unexpectedly returned')
    except (OSError,KeyboardInterrupt) as error:
        write_record(attempt/'status.json', {'status':'exec_outcome_unknown' if isinstance(error,KeyboardInterrupt) else 'exec_failed',
                     'profile':PROFILE,'mode':'exec','pid':os.getpid(),'parentPid':os.getppid(),'observedAt':time.time(),'hostReady':False,
                     'nativeToolsQualified':False,'bindingInstalled':False,'terminalSafety':'unknown','restarted':False})
        if isinstance(error,KeyboardInterrupt): raise
        raise Refusal('Public exec failed; intent stays consumed, no fallback or second launch') from None


def preview(path):
    spec = specification(path)
    return {'spec':spec,'reviewHash':review_hash(spec),'mode':'exec','startsHost':False,
            'nativeToolsQualified':False,'bindingInstalled':False,'migrationQualified':False,
            'boundary':'Application-owned launch review, not vendor desktop authorization, source-build attestation, credentials, terminal safety or Resume.'}


def status(attempt):
    # Historical journal only: never validate/reconnect today's socket or use
    # a process record as a cleanup/health claim. Unknown stays unknown.
    result=decode(private_file(Path(attempt)/'status.json').read_bytes())
    require(isinstance(result,dict) and set(result)=={'status','mode','profile','pid','parentPid','observedAt',
            'hostReady','nativeToolsQualified','bindingInstalled','terminalSafety','restarted'} and
            result['status'] in ('exec_boundary_issued','exec_failed','exec_outcome_unknown') and
            result['mode']=='exec' and result['profile']==PROFILE and result['terminalSafety']=='unknown' and
            all(result[k] is False for k in ('hostReady','nativeToolsQualified','bindingInstalled','restarted')) and
            all(type(result[k]) is int and result[k]>0 for k in ('pid','parentPid')) and
            type(result['observedAt']) in (int,float) and result['observedAt']>0,
            'Closed historical public launch record required')
    return {**result,'historical':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation',required=True)
    package = sub.add_parser('package-preview'); package.add_argument('root',type=Path)
    setup = sub.add_parser('setup-preview')
    for name in ('package','cwd','codex_home','socket_directory'): setup.add_argument(name,type=Path)
    review = sub.add_parser('preview'); review.add_argument('manifest',type=Path)
    execute = sub.add_parser('exec'); execute.add_argument('manifest',type=Path); execute.add_argument('attempt',type=Path)
    execute.add_argument('--confirm-hash',required=True)
    inspect_status = sub.add_parser('status'); inspect_status.add_argument('attempt',type=Path)
    args = parser.parse_args()
    try:
        if args.operation == 'package-preview':
            result = {'runtimePackage':inspect_package(args.root),'startsHost':False,'nativeToolsQualified':False}
        elif args.operation == 'setup-preview':
            result = {'spec':setup_scope(args.package,args.cwd,args.codex_home,args.socket_directory),
                      'startsHost':False,'nativeToolsQualified':False,'bindingInstalled':False}
        elif args.operation == 'preview': result = preview(args.manifest)
        elif args.operation == 'exec': exec_host(args.manifest,args.attempt,args.confirm_hash); return
        else: result = status(args.attempt)
        print(canonical(result))
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,'Public host refused: '+(str(error) if isinstance(error,Refusal) else 'private runtime unavailable')+'\n')


if __name__ == '__main__': main()
