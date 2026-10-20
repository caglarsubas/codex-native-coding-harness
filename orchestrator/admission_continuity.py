"""Read-only proof of one completed, approved empty-target registry transition.

No historical registry view, substituted hash, native call or authority grant.
Compare the actual before backup, complete canonical receipt and actual current
registry. The unused target may subsequently advance through normal controls;
all pre-transition rows and the setup draft remain retained.
"""
import copy
import hashlib
import math
import os
from pathlib import Path
import re
import uuid

from . import empty_setup_transition as setup, missions, projects, partial_admission
from .core import Ledger, canonical, digest, require
from .workspace_identity_recovery import file_pin
from .same_project_lifecycle import source_proof

PR184_SOURCE = '695980aef70da5bc77af9d49ac2d0185509c5a03a4dd2b1cbf3c13d852d06af3'
RECEIPT_FIELDS = {'kind','request','reviewHash','recordedAt','backupId','native','outcome','boundary'}
REQUEST_FIELDS = {'kind','version','sourceHash','workspaceId','spec','setupPins','catalogPin',
    'immutableSetupInputs','repositoryScope','configTransition','registration','oldCatalog','oldBindings',
    'newCatalogProject','originalMeta','draftHash','databases','boundary','preservedHoldPins'}


def implementation(expected, root, allowed):
    if expected == setup.source_hash():
        require(root is None, 'Current-source evidence needs no historical implementation substitute')
        return None
    require(expected == allowed and root is not None, 'Exact allowlisted immutable historical implementation required')
    proof = source_proof(root)
    require(proof['sourceHash'] == allowed, 'Historical implementation differs; never import or execute it')
    return proof


def archive_pin(path):
    """Only the caller's closed, verified database inventory may use this bound."""
    path = Path(path); file_pin(path); before = path.stat()
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        require(setup.file_identity(os.fstat(stream.fileno()))==setup.file_identity(before),'Historical database replaced before read')
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(setup.file_identity(os.fstat(stream.fileno()))==setup.file_identity(before),'Historical database changed while read')
    require(setup.file_identity(before) == setup.file_identity(path.stat()), 'Historical database file changed')
    return {'identity':[before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns],
        'fileIdentity':list(setup.file_identity(before)), 'sha256':sha}


def rows(db, table):
    require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', table), 'Closed SQL table name required')
    return {tuple(row) for row in db.execute('SELECT * FROM "'+table+'"')}


def schema(before, after, *, registry=False):
    query = 'SELECT type,name,tbl_name,sql FROM sqlite_master'
    old = {tuple(r[:3]):r[3] for r in before.execute(query)}
    now = {tuple(r[:3]):r[3] for r in after.execute(query)}
    require(all(now.get(key) == value for key,value in old.items()), 'Original SQL schema changed')
    extra = set(now)-set(old)
    permitted = {('table',setup.HISTORY,setup.HISTORY),
        ('index','sqlite_autoindex_'+setup.HISTORY+'_1',setup.HISTORY)} if registry and not any(
            key[0]=='table' and key[1]==setup.HISTORY for key in old) else set()
    require(extra == permitted, 'Unrelated schema addition refuses historical admission continuity')
    if registry:
        require([tuple(r)[1:6] for r in after.execute('PRAGMA table_info('+setup.HISTORY+')')] ==
            [('workspace','TEXT',0,None,1),('data','TEXT',1,None,0)], 'Exact transition history schema required')


def target_rows(before, after, request, receipt):
    schema(before, after)
    meta = Ledger.get(after,'meta',1); original = Ledger.get(before,'meta',1)
    require(original == request['originalMeta'] and original['brainId'] == request['spec']['oldBrainId'] and
        original.get('schemaVersion') == 1 and original.get('paused') is True and
        not any(key in original for key in ('standardRun','admissionBinding','brainHandoff','emptySetupTransition')) and
        not original.get('controller') and not original.get('runner'), 'Only the original unused pre-phase target qualifies')
    require(meta['brainId'] == request['spec']['brainId'] and meta.get('emptySetupTransition') == receipt['reviewHash'] and
        meta['revision'] >= original['revision']+1, 'Completed setup identity changed')
    old_repos = Ledger.all(before,'repos'); repos = Ledger.all(after,'repos')
    require(len(old_repos) == len(repos) == 1 and repos == [{**old_repos[0],
        'projectId':request['spec']['catalogProjectId']}], 'Only the reviewed one-checkout catalog mapping is supported')
    for table in setup.checked_fingerprint(before)['tables']:
        if table == 'sqlite_sequence':
            old_sequence,new_sequence=dict(rows(before,table)),dict(rows(after,table))
            require(all(name in new_sequence and new_sequence[name]>=value for name,value in old_sequence.items()),
                'Original target row sequences cannot regress')
            for name,value in new_sequence.items():
                require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) and
                    value==after.execute('SELECT MAX(rowid) FROM "'+name+'"').fetchone()[0],
                    'Target sequence must match retained append-only rows')
        elif table not in ('meta','repos'):
            require(rows(before,table) <= rows(after,table), 'A pre-transition target row was changed or removed')
    for name in ('commands','workers','queue','decisions','continuations'):
        require(not rows(before,name), 'Historical setup cannot dispose prior work or requests')
    if request['draftHash'] is not None:
        old = Ledger.get(before,'snapshots',request['draftHash']); matches = []
        for row in after.execute("SELECT id,data FROM snapshots WHERE kind='mission_configuration'"):
            candidate = setup.decode(row['data'])
            if candidate.get('previousHash') != request['draftHash'] or candidate.get('version') != old['version']+1: continue
            expected = {**old,'brainId':request['spec']['brainId'],'version':old['version']+1,
                'createdAt':candidate.get('createdAt'),'actor':'dashboard_owner','previousHash':request['draftHash'],
                'repositoryBindings':missions.bindings(repos,old['spec']['phase']['scope'])}
            require(candidate == expected and digest(candidate) == row['id'] and
                receipt['recordedAt'] <= candidate['createdAt'], 'Exact unreviewed setup successor draft must remain retained')
            matches.append(row['id'])
        require(len(matches) == 1, 'Missing or ambiguous original setup successor draft')


def registry_rows(before, after, request, receipt):
    schema(before, after, registry=True)
    tables = setup.checked_fingerprint(before)['tables']
    for table in tables:
        if table not in ('workspaces','project_catalog','project_bindings',setup.HISTORY):
            require(rows(before,table) == rows(after,table), 'An unrelated registry row changed')
    wanted = []
    for row in before.execute('SELECT * FROM workspaces ORDER BY id'):
        value = dict(row)
        if value['id'] == request['workspaceId']:
            require(value == request['registration'], 'Pre-transition registration backup differs')
            data = setup.decode(value['data']); data.update(brainId=request['spec']['brainId'],emptySetupTransition=receipt['reviewHash'])
            value.update(brain=data['brainId'],data=canonical(data))
        wanted.append(value)
    require([dict(r) for r in after.execute('SELECT * FROM workspaces ORDER BY id')] == wanted,
        'Only the exact reviewed registration change is allowed')
    old_catalog,old_bindings = projects._read(before)
    require(old_catalog == request['oldCatalog'] and old_bindings == request['oldBindings'], 'Original catalog snapshot differs')
    bindings = [dict(r) for r in before.execute('SELECT * FROM project_bindings') if r['workspace'] != request['workspaceId']]
    project = request['newCatalogProject']; data = setup.decode(request['registration']['data'])
    mapping = {'workspaceId':request['workspaceId'],'brainId':request['spec']['brainId'],
        'databaseIdentity':data['databaseIdentity'],'locationHash':project['locationHash']}
    bindings.append({'project_key':project['key'],'workspace':request['workspaceId'],'data':canonical(mapping)})
    require(sorted(bindings,key=lambda r:r['project_key']) == sorted(
        [dict(r) for r in after.execute('SELECT * FROM project_bindings')],key=lambda r:r['project_key']), 'Unrelated project mapping changed')
    catalog,_ = projects._read(after); observation = setup.read(request['spec']['catalogObservation'])
    normalized = projects.normalize(observation['completeResult'])
    require(catalog == {'source':projects.SOURCE,'observedAt':observation['observedAt'],
        'recordedAt':catalog['recordedAt'],'hash':digest(normalized),'projects':normalized} and
        receipt['recordedAt'] <= catalog['recordedAt'], 'Exact actual catalog transition required; no observation renewal')
    previous = rows(before,setup.HISTORY) if setup.HISTORY in tables else set()
    require(rows(after,setup.HISTORY) == previous | {(request['workspaceId'],canonical(receipt))},
        'The exact append-only completed transition history is required')


def validate(registry, ledger, target_id, *, setup_source=None):
    """No caller-supplied snapshot, current-hash override, socket or Git execution."""
    from .native_project_assignment import _registered
    root,_,_,_ = _registered(registry,target_id)
    require(target_id != ledger.workspace_id, 'The disposed source cannot be the transitioned target')
    receipt = setup.retained(root)
    require(receipt is not None and set(receipt) == RECEIPT_FIELDS and receipt['boundary'] == setup.BOUNDARY and
        receipt['kind'] == setup.KIND and receipt['outcome'] == 'registration_changed_execution_not_authorized',
        'Complete canonical positive setup receipt required; partial and forged history remain fenced')
    request = receipt['request']; spec = request['spec']
    require(set(request) == REQUEST_FIELDS and set(spec) == setup.SPEC_FIELDS and
        request['kind'] == spec['kind'] == setup.KIND and type(request['version']) is int and request['version'] == 1 and
        request['workspaceId'] == target_id == spec['workspaceId'] and request['boundary'] == setup.BOUNDARY and
        type(receipt['recordedAt']) in (float,int) and math.isfinite(receipt['recordedAt']) and receipt['recordedAt'] > 0,
        'Exact unused-target setup request required')
    native=receipt['native']
    require(set(native)=={'status','samples','currentPolicyQualified','independentLoadedPolicyPreviouslyMissing',
        'currentTerminalSafety','historicalTerminalSafety'} and native['status'] in ('idle','notLoaded') and
        type(native['samples']) is int and native['samples']==2 and native['currentPolicyQualified'] is False and
        native['independentLoadedPolicyPreviouslyMissing'] is True and
        native['currentTerminalSafety']==native['historicalTerminalSafety']=='unknown',
        'Original metadata readback is not policy, terminal safety or execution authority')
    require(request['registration']['root'] == str(root) and request['registration']['id'] == target_id and
        receipt['reviewHash'] == digest(request), 'Canonical setup scope/hash differs')
    proof = implementation(request['sourceHash'],setup_source,PR184_SOURCE)
    forbidden={'auth.json','credentials.json','.credentials.json','.env'}
    require(set(spec['setupRecords'])==setup.RECORDS and Path(spec['configFile']).name=='config.toml' and
        all(Path(p).name not in forbidden for p in spec['setupRecords'].values()),
        'Credentials are not historical setup evidence')
    require(setup.provenance(spec) == request['setupPins'] and setup.original_inputs(spec) == request['immutableSetupInputs'],
        'Original consumed setup claims, returned identities and epochs changed')
    require(setup.configuration(spec['configFile'],spec['checkout'],spec['originalConfigPin']) == request['configTransition'],
        'The exact originally reviewed configuration epochs changed')
    require(setup.pin(spec['catalogObservation']) == request['catalogPin'], 'Original catalog input changed')
    for value in request['preservedHoldPins'].values(): setup.preserved_pin(value)
    backup_id = receipt['backupId']
    require(isinstance(backup_id,str) and backup_id.startswith('empty-setup-') and
        str(uuid.UUID(backup_id[len('empty-setup-'):])) == backup_id[len('empty-setup-'):], 'Canonical source-created backup identifier required')
    directory = registry.root/'backups'/backup_id
    manifest = setup.read(directory/'manifest.json')
    require(set(manifest) == {'kind','reviewHash','databases','files'} and manifest['kind'] == setup.KIND and
        manifest['reviewHash'] == receipt['reviewHash'] and setup.read(directory/'request.json') == request,
        'Complete verified pre-transition backup required')
    expected = manifest['databases']
    require(isinstance(expected,list) and 2 <= len(expected) <= 33 and
        all(set(e)=={'original','proof','copy'} and e['copy']==str(index)+'.sqlite3' and
            e['proof']==request['databases'].get(e['original']) for index,e in enumerate(expected)) and
        len({e['original'] for e in expected}) == len(expected) and
        {e['original'] for e in expected}==set(request['databases']),
        'Every original registered database must have one exact backup')
    snapshots = {}; registered = None
    for entry in expected:
        path = Path(entry['original']); copy_path = directory/entry['copy']
        require([path.stat().st_dev,path.stat().st_ino] == entry['proof']['identity'], 'An original database was replaced')
        with setup.read_database(copy_path) as before,setup.read_database(path) as after:
            require(setup.checked_fingerprint(before) == entry['proof']['proof'], 'Pre-transition database proof differs')
            if path == registry.db:
                registered = {str(Path(r[0])/'ledger.sqlite3') for r in before.execute('SELECT root FROM workspaces')}
                registry_rows(before,after,request,receipt)
            elif path == root/'ledger.sqlite3': target_rows(before,after,request,receipt)
            else: require(setup.checked_fingerprint(after) == entry['proof']['proof'], 'An old run, ledger, request, usage or owner changed')
        snapshots[str(path)] = {'path':str(copy_path),'pin':archive_pin(copy_path)}
    require(registered is not None and set(request['databases']) == registered | {str(registry.db)} and
        str(ledger.db) in registered, 'The full original registry and disposed source must be covered')
    originals = {**{v['path']:v for v in request['setupPins'].values()},
        request['catalogPin']['path']:request['catalogPin'],spec['configFile']:setup.pin(spec['configFile']),
        **request['preservedHoldPins'], **{v['path']:v for v in request['immutableSetupInputs']}}
    files=manifest['files']
    require(isinstance(files,list) and len(files)==len(originals) and
        all(set(e)=={'original','pin','copy'} and e['copy']=='record-'+str(index)+'.json' and
            e['pin']==originals.get(e['original']) for index,e in enumerate(files)) and
        len({e['original'] for e in files})==len(files) and {e['original'] for e in files}==set(originals),
        'Complete original non-credential input backup inventory required')
    for entry in manifest['files']:
        setup.preserved_pin(entry['pin'])
        require(setup.pin(directory/entry['copy'])['sha256'] == entry['pin']['sha256'], 'Original setup backup changed')
    return {'targetId':target_id,'reviewHash':receipt['reviewHash'],'receiptPin':setup.pin(root/setup.RECEIPT),
        'claimPin':setup.pin(root/setup.FENCE),'setupSource':proof,'backupDirectory':str(directory),
        'manifestPin':setup.pin(directory/'manifest.json'),'requestPin':setup.pin(directory/'request.json'),
        'snapshots':snapshots}


def original_relation(registry, ledger, original, current, target_id, *, setup_source=None):
    proof = validate(registry,ledger,target_id,setup_source=setup_source)
    snapshot = proof['snapshots'][str(registry.db)]
    require(current['databases']['registry']==partial_admission.database_proof(registry.db),
        'The actual current registry proof must agree; no supplied current-hash override')
    with setup.read_database(registry.db) as db: current_catalog,_=projects._read(db)
    require(current['scope']['catalogHash']==current_catalog['hash'], 'Actual current catalog hash differs')
    require(original['databases']['registry']['identity'] == current['databases']['registry']['identity'],
        'Original registry identity must remain unchanged')
    before = partial_admission.database_proof(snapshot['path'])
    require(before['fingerprint'] == original['databases']['registry']['fingerprint'],
        'The retained setup backup does not anchor the original historical registry')
    left,right = copy.deepcopy(original),copy.deepcopy(current)
    # Compare complete actual records; only these two causally checked facts
    # differ. Never replace a current registry or rewrite a historical record.
    left['databases'].pop('registry'); right['databases'].pop('registry')
    left['scope'].pop('catalogHash'); right['scope'].pop('catalogHash')
    require(left == right, 'Unrelated original scope, claims, usage, binding or identity changed')
    with setup.read_database(snapshot['path']) as db: catalog,_ = projects._read(db)
    require(original['scope']['catalogHash'] == catalog['hash'], 'Historical catalog hash was not anchored before the transition')
    return proof
