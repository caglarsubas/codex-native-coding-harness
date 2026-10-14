"""Stage one explicit already-built monolithic package, never download or launch.

Uses only local existing inputs. Source/bundle/hash checks are provenance inputs,
not reproducible-build attestation or vendor desktop authorization. A failed or
interrupted staging directory is retained and never overwritten/retried.
"""
import argparse
import hashlib
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.core import canonical, require
from orchestrator.host_runtime import safe_path, stamp
from orchestrator.public_host_runtime import PROFILE, inspect_package


def git(argv):
    user=pwd.getpwuid(os.getuid())
    env={'HOME':user.pw_dir,'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull}
    result=subprocess.run(['/usr/bin/git','-c','core.fsmonitor=false','-c','core.hooksPath='+os.devnull,*argv],
                          env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20)
    require(result.returncode==0 and len(result.stdout.encode())<=65536,'Local source provenance read failed')
    return result.stdout


def stage(binary,binary_hash,bundle,bundle_hash,source,commit,tree,version,destination):
    binary,bundle,source,destination=map(Path,(binary,bundle,source,destination))
    binary_info,bundle_info=safe_path(binary),safe_path(bundle)
    require(binary_info.st_nlink==bundle_info.st_nlink==1 and binary_info.st_size<=512_000_000 and
            bundle_info.st_size<=512_000_000,'Bounded unaliased staging inputs required')
    safe_path(source,directory=True)
    pins=git(['-C',str(source),'rev-parse','HEAD','HEAD^{tree}']).splitlines()
    require(pins==[commit,tree] and not git(['-C',str(source),'status','--porcelain=v1']),
            'Exact clean local native source required')
    heads=git(['bundle','list-heads',str(bundle)]).splitlines()
    require(len(heads)==1 and len(heads[0].split())==2 and heads[0].split()[0]==commit and
            heads[0].split()[1].startswith('refs/heads/'), 'Source bundle must pin the exact sole native source branch')
    for file,info,expected in ((binary,binary_info,binary_hash),(bundle,bundle_info,bundle_hash)):
        fd=os.open(file,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            require(stamp(os.fstat(stream.fileno()))==stamp(info),'Staging input changed')
            require(hashlib.file_digest(stream,'sha256').hexdigest()==expected,'Exact already-reviewed staging hash required')
            require(stamp(os.fstat(stream.fileno()))==stamp(info)==stamp(file.lstat()),'Staging input changed during read')
    require(destination.is_absolute() and destination.parent.resolve(strict=True)==destination.parent,
            'Canonical new staging destination required')
    parent=safe_path(destination.parent,directory=True)
    require(parent.st_uid==os.getuid() and not parent.st_mode&0o077,'Owner-private staging parent required')
    destination.mkdir(mode=0o700)  # Exclusive; retain partial staging after any failure.
    (destination/'bin').mkdir(mode=0o700)
    shutil.copyfile(binary,destination/'bin/codex'); (destination/'bin/codex').chmod(0o500)
    shutil.copyfile(bundle,destination/'source.bundle'); (destination/'source.bundle').chmod(0o600)
    require(stamp(binary.lstat())==stamp(binary_info) and stamp(bundle.lstat())==stamp(bundle_info),
            'Staging input changed during copy')
    value={'schemaVersion':1,'profile':PROFILE,'trust':'operator_reviewed_build_v1','desktopBridge':'absent',
           'target':'aarch64-apple-darwin','version':version,'sourceCommit':commit,'sourceTree':tree,
           'sourceBundleSha256':bundle_hash,'executableSha256':binary_hash,'entrypoint':'bin/codex',
           'helperMode':'monolithic_arg0','dependencies':'macos_system_libraries_only'}
    fd=os.open(destination/'public-runtime.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    pin=inspect_package(destination)
    return {'runtimePackage':pin,'startsHost':False,'buildAttested':False,'desktopAuthorized':False,
            'nativeToolsQualified':False,'bindingInstalled':False,'migrationQualified':False}


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','binary_hash','bundle','bundle_hash','source','commit','tree','version','destination'):
        parser.add_argument('--'+name.replace('_','-'),required=True)
    args=parser.parse_args()
    print(canonical(stage(**vars(args))))
