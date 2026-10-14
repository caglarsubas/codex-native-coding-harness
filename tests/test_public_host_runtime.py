import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from orchestrator.core import Refusal
from orchestrator.host_lifecycle import validate_spec as vendor_spec
from orchestrator.public_host_runtime import PROFILE, inspect_package, system_libraries, validate_pin
from orchestrator import public_host_lifecycle as lifecycle


def macho(library='/usr/lib/libSystem.B.dylib', extra=b''):
    name = library.encode()+b'\0'
    size = (24+len(name)+7)//8*8
    command = struct.pack('<6I',0xc,size,24,0,0,0)+name
    command += b'\0'*(size-len(command))
    commands = command+extra
    return struct.pack('<8I',0xfeedfacf,0x100000c,0,2,1+bool(extra),len(commands),0,0)+commands+b'fixture-only-no-machine-code'


def package_fixture(root, payload=None):
    root.mkdir(mode=0o700); (root/'bin').mkdir(mode=0o700)
    binary = root/'bin/codex'; binary.write_bytes(payload or macho()); binary.chmod(0o500)
    bundle = root/'source.bundle'; bundle.write_bytes(b'fixture-source-bundle'); bundle.chmod(0o600)
    layout = {'schemaVersion':1,'profile':PROFILE,'trust':'operator_reviewed_build_v1','desktopBridge':'absent',
              'target':'aarch64-apple-darwin','version':'fixture.1','sourceCommit':'a'*40,'sourceTree':'b'*40,
              'sourceBundleSha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
              'executableSha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'entrypoint':'bin/codex',
              'helperMode':'monolithic_arg0','dependencies':'macos_system_libraries_only'}
    (root/'public-runtime.json').write_text(json.dumps(layout)); (root/'public-runtime.json').chmod(0o600)
    return inspect_package(root)


class PublicRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ph.',dir='/private/tmp' if Path('/private/tmp').exists() else None)
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.package = self.root/'pkg'; self.pin = package_fixture(self.package)

    def tearDown(self): self.temp.cleanup()

    def test_inspection_is_non_executing_and_pins_all_required_bytes(self):
        with patch('subprocess.run') as run, patch('subprocess.Popen') as popen, patch('os.execve') as execute:
            self.assertEqual(inspect_package(self.package),self.pin); validate_pin(self.pin)
        run.assert_not_called(); popen.assert_not_called(); execute.assert_not_called()
        self.assertEqual(self.pin['fileCount'],3)
        self.assertNotIn('vendorSigned',self.pin)

    def test_every_component_is_required(self):
        for path in ('public-runtime.json','bin/codex','source.bundle'):
            file = self.package/path; data,mode = file.read_bytes(),file.stat().st_mode&0o777
            file.unlink()
            with self.subTest(path=path),self.assertRaises((Refusal,OSError)): inspect_package(self.package)
            file.write_bytes(data); file.chmod(mode)

    def test_binary_and_source_hash_must_match_manifest(self):
        (self.package/'bin/codex').chmod(0o700)
        for path in ('bin/codex','source.bundle'):
            file=self.package/path; data=file.read_bytes(); file.write_bytes(data+b'changed')
            with self.subTest(path=path),self.assertRaises(Refusal): inspect_package(self.package)
            file.write_bytes(data)

    def test_same_bytes_replacement_and_permissions_invalidate_review(self):
        file=self.package/'source.bundle'; replacement=self.package/'next'
        replacement.write_bytes(file.read_bytes()); replacement.chmod(0o600); os.replace(replacement,file)
        with self.assertRaises(Refusal): validate_pin(self.pin)
        current=inspect_package(self.package); file.chmod(0o644)
        with self.assertRaises(Refusal): validate_pin(current)

    def test_extra_files_directories_or_credentials_are_not_inherited(self):
        for name in ('codex-code-mode-host','auth.json','.env','plugin.json'):
            file=self.package/name; file.write_text('PRIVATE')
            with self.subTest(name=name),self.assertRaises(Refusal): inspect_package(self.package)
            file.unlink()
        (self.package/'bin/rg').write_text('unexpected dependency')
        with self.assertRaises(Refusal): inspect_package(self.package)

    def test_symlinks_hardlinks_special_files_and_unsafe_ancestors_refuse(self):
        file=self.package/'source.bundle'; data=file.read_bytes(); file.unlink(); file.symlink_to(self.package/'bin/codex')
        with self.assertRaises(Refusal): inspect_package(self.package)
        file.unlink(); os.mkfifo(file)
        with self.assertRaises(Refusal): inspect_package(self.package)
        file.unlink(); file.write_bytes(data); file.chmod(0o600)
        alias=self.root/'alias'; os.link(file,alias)
        with self.assertRaises(Refusal): inspect_package(self.package)
        alias.unlink(); self.root.chmod(0o777)
        with self.assertRaises(Refusal): inspect_package(self.package)
        self.root.chmod(0o700)

    def test_manifest_is_closed_and_vendor_identity_is_never_substituted(self):
        file=self.package/'public-runtime.json'; original=json.loads(file.read_text())
        for key,value in (('profile','standard_owned_host_v1'),('desktopBridge','vendor'),('schemaVersion',True),
                          ('sourceTree','z'*40),('target','x86_64-apple-darwin'),('helperMode','external')):
            altered={**original,key:value}; file.write_text(json.dumps(altered))
            with self.subTest(key=key),self.assertRaises(Refusal): inspect_package(self.package)
        file.write_text(json.dumps({**original,'vendorSigned':True}))
        with self.assertRaises(Refusal): inspect_package(self.package)

    def test_external_libraries_loader_paths_and_rpaths_refuse(self):
        binary=self.package/'bin/codex'; binary.chmod(0o700)
        for name in ('@rpath/libprivate.dylib','@loader_path/helper','/opt/homebrew/lib/helper.dylib',
                     '/usr/lib/../private/lib.dylib'):
            binary.write_bytes(macho(name))
            with self.subTest(name=name),self.assertRaises(Refusal): system_libraries(binary)
        for command in (0x8000001c,0x27):
            binary.write_bytes(macho(extra=struct.pack('<2I',command,8)))
            with self.subTest(command=command),self.assertRaises(Refusal): system_libraries(binary)

    def test_truncated_invalid_headers_and_dependency_offsets_refuse(self):
        binary=self.package/'bin/codex'; binary.chmod(0o700); good=macho()
        for data in (good[:10],good[:40],b'not a Mach-O executable'*4,
                     good[:4]+struct.pack('<I',0x1000007)+good[8:],good[:40]+struct.pack('<I',0)+good[44:]):
            binary.write_bytes(data)
            with self.subTest(size=len(data)),self.assertRaises(Refusal): system_libraries(binary)

    def test_duplicate_manifest_keys_are_not_normalized(self):
        file=self.package/'public-runtime.json'
        file.write_text(file.read_text()[:-1]+',"schemaVersion":1}')
        with self.assertRaises(Refusal): inspect_package(self.package)


class PublicLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ph.',dir='/private/tmp' if Path('/private/tmp').exists() else None)
        self.root=Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.package=self.root/'pkg'; package_fixture(self.package)
        self.cwd=self.root/'repo'; self.cwd.mkdir(mode=0o700); (self.cwd/'.git').mkdir(mode=0o700)
        self.home=self.root/'home'; self.home.mkdir(mode=0o700)
        self.sockets=self.root/'ipc'; self.sockets.mkdir(mode=0o700)
        (self.home/'config.toml').write_text(lifecycle.CONFIG); (self.home/'config.toml').chmod(0o600)
        self.spec=lifecycle.setup_scope(self.package,self.cwd,self.home,self.sockets)
        self.manifest=self.root/'manifest.json'; self.manifest.write_text(json.dumps(self.spec)); self.manifest.chmod(0o600)
        self.attempt=self.root/'attempt'

    def tearDown(self): self.temp.cleanup()

    def test_preview_makes_no_process_or_native_claim_and_no_authority(self):
        with patch('os.execve') as execute,patch('subprocess.Popen') as popen:
            report=lifecycle.preview(self.manifest)
        self.assertFalse(report['startsHost']); self.assertFalse(report['migrationQualified'])
        self.assertFalse(report['bindingInstalled']); execute.assert_not_called(); popen.assert_not_called()
        self.assertFalse(self.attempt.exists())

    def test_fixed_environment_drops_all_desktop_secrets_and_preloads(self):
        injected={'CODEX_APP_TOOLS_PIPE_PATH':'PRIVATE','CODEX_APP_SERVER_URL':'PRIVATE','OPENAI_API_KEY':'PRIVATE',
                  'HTTPS_PROXY':'PRIVATE','DYLD_INSERT_LIBRARIES':'PRIVATE','PATH':'/evil','CODEX_HOME':'/evil'}
        with patch.dict(os.environ,injected): env=lifecycle.environment(self.spec)
        self.assertEqual(env['PATH'],'/usr/bin:/bin'); self.assertEqual(env['CODEX_HOME'],str(self.home))
        self.assertEqual(set(env),{'HOME','USER','LOGNAME','PATH','CODEX_HOME','TMPDIR'})
        self.assertNotIn('PRIVATE',str(env)); self.assertNotEqual(env['TMPDIR'],env['CODEX_HOME'])

    def test_fixed_config_disables_login_shells_and_child_environment_inheritance(self):
        config=tomllib.loads(lifecycle.CONFIG)
        self.assertIs(config['allow_login_shell'],False)
        self.assertEqual(config['shell_environment_policy'],{'inherit':'none','set':{'PATH':'/usr/bin:/bin','LANG':'C'}})
        self.assertEqual(config['cli_auth_credentials_store'],'file')
        self.assertIs(config['sandbox_workspace_write']['network_access'],False)
        self.assertFalse(any(config['features'][k] for k in ('code_mode','code_mode_only','apps','plugins','hooks')))

    def test_credentials_plugins_dotenv_native_state_and_sockets_refuse(self):
        for name in ('auth.json','.env','sessions','plugins','config.extra.toml'):
            file=self.home/name; file.write_text('PRIVATE')
            with self.subTest(name=name),self.assertRaises(Refusal): lifecycle.validate_spec(self.spec)
            file.unlink()
        (self.sockets/'old.sock').write_text('not an empty socket directory')
        with self.assertRaises(Refusal): lifecycle.validate_spec(self.spec)

    def test_configuration_widening_or_same_bytes_replacement_refuses(self):
        file=self.home/'config.toml'; original=file.read_text(); file.write_text(original+'\n[external]\n')
        with self.assertRaises(Refusal): lifecycle.validate_spec(self.spec)
        file.write_text(original)
        with self.assertRaises(Refusal): lifecycle.validate_spec(self.spec)

    def test_unsafe_home_overlap_nonrepo_and_project_config_refuse(self):
        self.home.chmod(0o755)
        with self.assertRaises(Refusal): lifecycle.validate_spec(self.spec)
        self.home.chmod(0o700)
        with self.assertRaises(Refusal): lifecycle.setup_scope(self.package,self.cwd,self.home,self.home)
        (self.cwd/'.git').rmdir()
        with self.assertRaises(Refusal): lifecycle.setup_scope(self.package,self.cwd,self.home,self.sockets)
        (self.cwd/'.git').mkdir(); (self.cwd/'config.toml').write_text('extra')
        with self.assertRaises(Refusal): lifecycle.setup_scope(self.package,self.cwd,self.home,self.sockets)

    def test_vendor_review_and_public_review_are_incompatible(self):
        with self.assertRaises(Refusal): vendor_spec(self.spec)
        with self.assertRaises(Refusal): lifecycle.validate_spec({'schemaVersion':2,'profile':'standard_owned_host_v1'})
        self.assertNotEqual(lifecycle.review_hash(self.spec),digest_vendor(self.spec))

    def test_wrong_review_or_platform_has_no_intent_or_process_boundary(self):
        with patch('os.execve') as execute,patch.object(lifecycle.sys,'platform','darwin'),patch.object(lifecycle.platform,'machine',return_value='arm64'):
            with self.assertRaises(Refusal): lifecycle.exec_host(self.manifest,self.attempt,'wrong')
        execute.assert_not_called(); self.assertFalse(self.attempt.exists())
        with patch.object(lifecycle.sys,'platform','linux'),self.assertRaises(Refusal):
            lifecycle.exec_host(self.manifest,self.attempt,lifecycle.review_hash(self.spec))
        self.assertFalse(self.attempt.exists())

    def test_exec_claim_precedes_single_exact_exec_and_no_native_rpc(self):
        with patch.object(lifecycle.sys,'platform','darwin'),patch.object(lifecycle.platform,'machine',return_value='arm64'),\
             patch.object(lifecycle.os,'chdir'),patch.object(lifecycle.os,'dup2'),\
             patch.object(lifecycle.os,'execve',side_effect=OSError('PRIVATE_EXEC_ERROR')) as execute:
            with self.assertRaises(Refusal): lifecycle.exec_host(self.manifest,self.attempt,lifecycle.review_hash(self.spec))
            self.assertTrue((self.attempt/'exec.claim').exists())
            with self.assertRaises(Refusal): lifecycle.exec_host(self.manifest,self.attempt,lifecycle.review_hash(self.spec))
        self.assertEqual(execute.call_count,1)
        binary=str(self.package/'bin/codex')
        self.assertEqual(execute.call_args.args[:2],(binary,[binary,'app-server','--listen','unix://'+str(self.sockets/'host.sock')]))
        self.assertEqual(execute.call_args.args[2],lifecycle.environment(self.spec))
        record=json.loads((self.attempt/'status.json').read_text())
        self.assertEqual(record['status'],'exec_failed'); self.assertFalse(record['hostReady']); self.assertFalse(record['restarted'])
        self.assertEqual(record['terminalSafety'],'unknown')
        self.assertNotIn('PRIVATE_EXEC_ERROR',(self.attempt/'status.json').read_text())

    def test_post_claim_drift_is_consumed_without_exec_or_fallback(self):
        original=lifecycle.validate_spec; calls=[]
        def check(spec):
            calls.append(None)
            if len(calls)==2: raise Refusal('fixture drift')
            return original(spec)
        with patch.object(lifecycle.sys,'platform','darwin'),patch.object(lifecycle.platform,'machine',return_value='arm64'),\
             patch.object(lifecycle,'validate_spec',side_effect=check),patch.object(lifecycle.os,'execve') as execute:
            with self.assertRaises(Refusal): lifecycle.exec_host(self.manifest,self.attempt,lifecycle.review_hash(self.spec))
        self.assertTrue((self.attempt/'launch.json').exists()); self.assertTrue((self.attempt/'exec.claim').exists())
        execute.assert_not_called()

    def test_persistence_interruption_keeps_intent_and_never_executes(self):
        with patch.object(lifecycle.sys,'platform','darwin'),patch.object(lifecycle.platform,'machine',return_value='arm64'),\
             patch.object(lifecycle,'write_record',side_effect=OSError('PRIVATE')),patch.object(lifecycle.os,'execve') as execute:
            with self.assertRaises(OSError): lifecycle.exec_host(self.manifest,self.attempt,lifecycle.review_hash(self.spec))
        self.assertTrue(self.attempt.exists()); execute.assert_not_called()

    def test_interruption_after_exec_boundary_keeps_unknown_status(self):
        with patch.object(lifecycle.sys,'platform','darwin'),patch.object(lifecycle.platform,'machine',return_value='arm64'),\
             patch.object(lifecycle.os,'chdir'),patch.object(lifecycle.os,'dup2'),\
             patch.object(lifecycle.os,'execve',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): lifecycle.exec_host(self.manifest,self.attempt,lifecycle.review_hash(self.spec))
        self.assertEqual(json.loads((self.attempt/'status.json').read_text())['status'],'exec_outcome_unknown')

    def test_status_is_closed_historical_and_cannot_claim_native_health(self):
        self.attempt.mkdir(mode=0o700)
        record={'status':'exec_boundary_issued','profile':PROFILE,'mode':'exec','pid':123,'parentPid':456,
                'observedAt':1,'hostReady':False,'nativeToolsQualified':False,'bindingInstalled':False,
                'terminalSafety':'unknown','restarted':False}
        path=self.attempt/'status.json'; path.write_text(json.dumps(record)); path.chmod(0o600)
        with patch('subprocess.Popen') as popen,patch('os.execve') as execute:
            self.assertTrue(lifecycle.status(self.attempt)['historical'])
        popen.assert_not_called(); execute.assert_not_called()
        for key,value in (('hostReady',True),('terminalSafety','none'),('nativeToolsQualified',0),('credential','PRIVATE')):
            path.write_text(json.dumps({**record,key:value}))
            with self.subTest(key=key),self.assertRaises(Refusal): lifecycle.status(self.attempt)

    def test_attempt_inside_pinned_scope_and_mutated_policy_refuse(self):
        with patch.object(lifecycle.sys,'platform','darwin'),patch.object(lifecycle.platform,'machine',return_value='arm64'),\
             patch.object(lifecycle.os,'execve') as execute:
            with self.assertRaises(Refusal): lifecycle.exec_host(self.manifest,self.home/'attempt',lifecycle.review_hash(self.spec))
        execute.assert_not_called()
        self.spec['nativePolicy']['codeMode']=0
        with self.assertRaises(Refusal): lifecycle.validate_spec(self.spec)


class PublicStagingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ph.',dir='/private/tmp' if Path('/private/tmp').exists() else None)
        self.root=Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.source=self.root/'source'; self.source.mkdir(mode=0o700)
        self.binary=self.root/'codex'; self.binary.write_bytes(macho()); self.binary.chmod(0o500)
        self.bundle=self.root/'source.bundle'; self.bundle.write_bytes(b'fixture-bundle'); self.bundle.chmod(0o600)
        self.dest=self.root/'staged'
        module=importlib.util.spec_from_file_location('public_stager',Path(__file__).parents[1]/'scripts/stage_public_runtime.py')
        self.stager=importlib.util.module_from_spec(module); module.loader.exec_module(self.stager)
        self.args={'binary':str(self.binary),'binary_hash':hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                   'bundle':str(self.bundle),'bundle_hash':hashlib.sha256(self.bundle.read_bytes()).hexdigest(),
                   'source':str(self.source),'commit':'a'*40,'tree':'b'*40,'version':'fixture.1','destination':str(self.dest)}

    def tearDown(self): self.temp.cleanup()

    def git(self,argv):
        if 'rev-parse' in argv: return 'a'*40+'\n'+'b'*40+'\n'
        if 'status' in argv: return ''
        return 'a'*40+' refs/heads/codex/fixture\n'

    def test_staging_is_exclusive_no_download_launch_or_native_effect(self):
        with patch.object(self.stager,'git',side_effect=self.git),patch('subprocess.Popen') as popen,patch('os.execve') as execute:
            result=self.stager.stage(**self.args)
            with self.assertRaises(FileExistsError): self.stager.stage(**self.args)
        popen.assert_not_called(); execute.assert_not_called()
        self.assertFalse(result['startsHost']); self.assertFalse(result['buildAttested']); self.assertFalse(result['desktopAuthorized'])
        self.assertFalse(result['migrationQualified']); self.assertEqual(result['runtimePackage'],inspect_package(self.dest))

    def test_wrong_source_or_hash_cannot_create_staging(self):
        for field in ('commit','tree','binary_hash','bundle_hash'):
            args={**self.args,field:'c'*(40 if field in ('commit','tree') else 64)}
            with patch.object(self.stager,'git',side_effect=self.git),self.subTest(field=field),self.assertRaises(Refusal):
                self.stager.stage(**args)
            self.assertFalse(self.dest.exists())

    def test_dirty_source_multiple_bundle_heads_and_unpinned_branch_refuse(self):
        for bad in ('dirty','two-heads','wrong-head'):
            def query(argv):
                if bad=='dirty' and 'status' in argv: return ' M source.rs\n'
                if 'list-heads' in argv:
                    return ('a'*40+' refs/heads/one\n'+'a'*40+' refs/heads/two\n') if bad=='two-heads' else 'c'*40+' refs/heads/one\n'
                return self.git(argv)
            with patch.object(self.stager,'git',side_effect=query),self.subTest(bad=bad),self.assertRaises(Refusal):
                self.stager.stage(**self.args)
            self.assertFalse(self.dest.exists())

    def test_partial_copy_stays_retained_and_cannot_retry(self):
        with patch.object(self.stager,'git',side_effect=self.git),patch.object(self.stager.shutil,'copyfile',side_effect=OSError('fixture')):
            with self.assertRaises(OSError): self.stager.stage(**self.args)
        self.assertTrue(self.dest.is_dir())
        with patch.object(self.stager,'git',side_effect=self.git),self.assertRaises(FileExistsError): self.stager.stage(**self.args)

    def test_parent_alias_and_world_readable_private_parent_refuse(self):
        alias=self.root/'alias'; alias.symlink_to(self.root,target_is_directory=True)
        with patch.object(self.stager,'git',side_effect=self.git),self.assertRaises(Refusal):
            self.stager.stage(**{**self.args,'destination':str(alias/'staged')})
        self.root.chmod(0o755)
        with patch.object(self.stager,'git',side_effect=self.git),self.assertRaises(Refusal): self.stager.stage(**self.args)
        self.root.chmod(0o700)


def digest_vendor(spec):
    from orchestrator.core import digest
    return digest({'manifestHash':digest(spec),'mode':'exec'})
