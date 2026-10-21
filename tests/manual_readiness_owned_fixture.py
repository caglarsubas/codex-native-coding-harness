"""Disposable rendered review; native RPCs are the labelled unit fixture only."""
import json
import os
import signal
import socket
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from orchestrator import readiness_owned as owned, standard
from orchestrator.public_pilot_inspection import exclusive
from orchestrator.public_host_restart import pin
from test_readiness_owned import ReadinessOwnedTest

if __name__ == '__main__':
    signal.signal(signal.SIGINT,signal.default_int_handler)
    http_thread=threading.Thread
    http_socket=socket.socket
    historical_admission='--historical-admission' in sys.argv[1:]
    admitted='--admitted' in sys.argv[1:] or historical_admission
    if admitted:
        from test_admitted_readiness import AdmittedReadinessTest
        owner_fixture=AdmittedReadinessTest('runTest')
        owner_fixture.historical_source=historical_admission
        owner_fixture.setUp(); fixture=owner_fixture.r
    else:
        owner_fixture=ReadinessOwnedTest('runTest'); owner_fixture.setUp(); fixture=owner_fixture
    confirm_browser='--confirm-browser' in sys.argv[1:]
    old=fixture.ledger.root/'public-preplay-load-consumed.claim'
    exclusive(old,{'fixture':'consumed original inspection','usageGap':'unknown'})
    os.utime(old,ns=(1792000000000000001,1792000000000000001))
    old_bytes=old.read_bytes(); old_identity=pin(old)['identity']
    registry_before=owned.partial.database_proof(fixture.registry.db)
    snapshot_before=fixture.ledger.snapshot()
    # The unit fake suppresses observer threads. HTTP handlers need real
    # threads. Opt-in confirmation validates the real HTTP/local transaction,
    # but never invokes the notifier, load or turn, even on the fake host.
    threading.Thread=http_thread
    if admitted:
        # The historical fixture forbids every native socket. Permit only the
        # disposable HTTP listener; outbound native connections remain denied.
        class HttpOnlySocket(http_socket):
            def bind(self,address):
                assert address[0]=='127.0.0.1','Disposable loopback listener only'
                return super().bind(address)
            def connect(self,*args): raise AssertionError('No native connection')
            def connect_ex(self,*args): raise AssertionError('No native connection')
        socket.socket=HttpOnlySocket
    server=Dashboard(fixture.ledger,0,registry=fixture.registry,
        runtime_root=Path(__file__).resolve().parents[1],inference_env=fixture.f.root/'absent.env')
    server.daemon_threads=False
    runtime=server.runtime_for(fixture.ledger.workspace_id); runtime.notifier.app_server=fixture.wake
    if confirm_browser: runtime.notify_control=lambda command:command
    runtime.brain_activity.snapshot=lambda *_:{'status':'unknown','observedAt':None}
    runtime.task_activity.snapshot=lambda *_:{}
    server.bootstrap='disposable-readiness-owned-fixture'
    display_identity=([str(n) for n in owner_fixture.original_continuity_pin['identity']]
                      if historical_admission else None)
    print(json.dumps({'origin':server.origin,'token':server.bootstrap,'workspace':fixture.ledger.workspace_id,
                     'historicalAdmission':historical_admission,'continuityIdentityDecimal':display_identity}),flush=True)
    before=fixture.f.proof()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()  # Finish in-flight fixture reads before cleanup.
        if confirm_browser:
            after=fixture.ledger.snapshot(); commands=after['commands']
            assert len(commands)==1,'Browser must confirm exactly one new command'
            command=commands[0]; review=command['payload']['readinessStart']
            assert review['local']['sidecars'][old.name]['identity']==old_identity
            assert 1792000000000000001 in old_identity,'Fixture must retain an unsafe JavaScript integer'
            if historical_admission:
                assert review['local']['workerAdmission']['sourceContinuityPin']==owner_fixture.original_continuity_pin
                assert 1792000000000000001 in review['local']['workerAdmission']['sourceContinuityPin']['identity']
                assert all(type(n) is int for n in review['local']['workerAdmission']['sourceContinuityPin']['identity'])
            assert command['kind']=='standard_catalog_refresh' and command['status']=='queued'
            assert command.get('notification',{}).get('status')!='accepted'
            assert len(owned.claims(fixture.ledger))==1
            assert owned.record(owned.fence(fixture.ledger))['commandId']==command['id']
            assert standard.read(fixture.ledger)['run'] is None
            for key in ('workers','queue','decisions','repositories'):
                assert after.get(key)==snapshot_before.get(key),'Old fixture inventory changed: '+key
            meta_before=snapshot_before['meta'].copy(); meta_after=after['meta'].copy()
            meta_before.pop('revision',None); meta_after.pop('revision',None)
            assert meta_before==meta_after,'No phase, usage, policy or ownership mutation'
        else:
            assert before==fixture.f.proof(),'Preview must not create a command or change old state'
        assert registry_before==owned.partial.database_proof(fixture.registry.db)
        assert old.read_bytes()==old_bytes and pin(old)['identity']==old_identity
        assert not fixture.calls or all(m not in ('thread/resume','turn/start') for m,_ in fixture.calls)
        if admitted: owner_fixture.conserved()
        owner_fixture.doCleanups()
