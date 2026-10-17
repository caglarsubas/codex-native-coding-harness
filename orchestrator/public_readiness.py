"""Prospective public-backend capability evidence, not desktop-tool discovery.

The reviewed binary exports its own versioned schemas in a disposable empty
home. Only the original owned connection reads models, identity and policy.
Neither the export nor a model catalog proves entitlement, execution or cleanup.
"""
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .core import digest, require
from .native_read_client import decode, secure_path, file_identity, validate_endpoint
from .native_policy_evidence import collect as policy_collect, matches
from .public_native_tasks import validate_contract, arguments, PROTOCOL

VERSION = 1
SOURCE = 'public_backend_schema_and_catalog_v1'
SCHEMAS = ('ThreadStartParams', 'TurnStartParams', 'ModelListParams', 'ModelListResponse')
EFFORTS = {'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}
BOUNDARY = {'desktopToolsQualified': False, 'modelEntitlementVerified': False,
            'executionAuthorized': False, 'nativeLoadMade': False,
            'terminalSafety': 'unknown', 'historicalCleanupVerified': False}


def accepts(schema, value, root, depth=0):
    """Closed subset needed by our fixed public task arguments, not a schema SDK."""
    require(isinstance(schema, dict) and depth < 16, 'Unsupported public request schema')
    require(set(schema) <= {'$ref', '$schema', 'title', 'description', 'default', 'definitions',
        'type', 'enum', 'allOf', 'anyOf', 'oneOf', 'properties', 'required', 'additionalProperties',
        'items', 'minItems', 'maxItems', 'minLength', 'maxLength', 'pattern', 'minimum', 'maximum', 'format'},
        'Unsupported native schema constraint; never ignore it')
    if '$ref' in schema:
        ref = schema['$ref']
        require(isinstance(ref, str) and ref.startswith('#/definitions/') and ref.count('/') == 2,
                'Only local native schema definitions are supported')
        if not accepts(root['definitions'][ref.rsplit('/', 1)[1]], value, root, depth+1):
            return False
    for union in ('allOf', 'anyOf', 'oneOf'):
        if union in schema:
            require(isinstance(schema[union], list) and schema[union], 'Native schema union is incomplete')
            count = sum(accepts(branch, value, root, depth+1) for branch in schema[union])
            if not (count == len(schema[union]) if union == 'allOf' else count == 1 if union == 'oneOf' else count > 0):
                return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    types = schema.get('type', [])
    if isinstance(types, str):
        types = [types]
    actual = ('null' if value is None else 'boolean' if type(value) is bool else
              'string' if isinstance(value, str) else 'object' if isinstance(value, dict) else
              'array' if isinstance(value, list) else 'integer' if type(value) is int else 'number')
    if types and actual not in types and not (actual == 'integer' and 'number' in types):
        return False
    if isinstance(value, str):
        return schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', len(value)) and (
            'pattern' not in schema or re.search(schema['pattern'], value) is not None)
    if type(value) in (int, float):
        require(schema.get('format') in (None, 'uint32', 'uint', 'int64'), 'Unsupported native numeric format')
        return math.isfinite(value) and schema.get('minimum', value) <= value <= schema.get('maximum', value) and (
            schema.get('format') != 'uint32' or type(value) is int and 0 <= value <= 4294967295)
    if isinstance(value, dict):
        props = schema.get('properties', {})
        return all(k in value for k in schema.get('required', [])) and all(
            accepts(props[k], v, root, depth+1) if k in props else
            accepts(schema['additionalProperties'], v, root, depth+1) if isinstance(schema.get('additionalProperties'), dict)
            else schema.get('additionalProperties', True) is True for k, v in value.items())
    if isinstance(value, list):
        return schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)) and (
            'items' not in schema or all(accepts(schema['items'], v, root, depth+1) for v in value))
    return True


def schema_contract(schemas):
    require(set(schemas) == set(SCHEMAS), 'Complete versioned public schemas required')
    required = {
        'ThreadStartParams': {'cwd', 'projectId', 'model', 'approvalPolicy', 'approvalsReviewer', 'sandbox', 'config', 'ephemeral'},
        'TurnStartParams': {'threadId', 'input', 'model', 'effort', 'approvalPolicy', 'approvalsReviewer'},
        'ModelListParams': {'cursor', 'limit', 'includeHidden'},
        'ModelListResponse': {'data', 'nextCursor'}}
    for name, fields in required.items():
        require(schemas[name].get('type') == 'object' and fields <= set(schemas[name].get('properties', {})),
                'Public adapter fields are not exposed by this native binary')
    backend = {'protocol': PROTOCOL, 'sourceCommit': 'a'*40, 'sourceTree': 'b'*40,
               'trust': 'operator_reviewed_build_v1', 'desktopBridge': 'absent', 'repositoryMode': 'repo_exclusive'}
    seed = {'task': {'model': 'schema-only', 'effort': 'high', 'paths': []},
            'repository': {'path': '/disposable'}, 'mission': {'fixture': True},
            'instructions': 'Schema validation only', 'acceptance': ['No native effect']}
    start, turn = arguments(seed, {'cwd': '/disposable', 'projectId': '00000000-0000-4000-8000-000000000001',
        'nativeTaskBackend': backend, 'policyEvidence': {'protocol': 'loaded_thread_policy_v1',
            'sourceCommit': 'a'*40, 'sourceTree': 'b'*40}})
    turn = {'threadId': '00000000-0000-4000-8000-000000000002', **turn}
    require(accepts(schemas['ThreadStartParams'], start, schemas['ThreadStartParams']) and
            accepts(schemas['TurnStartParams'], turn, schemas['TurnStartParams']) and
            accepts(schemas['ModelListParams'], {'cursor': None, 'limit': 30, 'includeHidden': False}, schemas['ModelListParams']),
            'The native schemas do not accept the fixed restricted public adapter arguments')
    return {'protocol': PROTOCOL, 'schemaHashes': {k: digest(v) for k,v in schemas.items()},
            'methods': ['thread/start', 'turn/start'], 'experimentalFields': True}


def export_schemas(executable, expected_hash):
    binary, before = secure_path(executable)
    require(hashlib.sha256(binary.read_bytes()).hexdigest() == expected_hash, 'Reviewed schema executable changed')
    epoch = file_identity(before)
    with tempfile.TemporaryDirectory(prefix='codex-public-readiness-') as directory:
        root = Path(directory).resolve(); root.chmod(0o700)
        home = root/'home'; home.mkdir(mode=0o700)
        output = root/'schema'
        # No inherited credentials, plugin roots, proxy or desktop pipe. This
        # fixed schema-export command starts no app-server and reads no brain.
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'CODEX_HOME': str(home), 'TMPDIR': str(root)}
        try:
            result = subprocess.run([str(binary), 'app-server', 'generate-json-schema', '--experimental', '--out', str(output)],
                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=20, close_fds=True)
        except (OSError, subprocess.TimeoutExpired):
            require(False, 'Versioned native schema export unavailable; no fallback or retry')
        require(result.returncode == 0, 'Versioned native schema export unavailable')
        schemas = {}
        for name in SCHEMAS:
            file = output/'v2'/(name+'.json')
            require(file.is_file() and not file.is_symlink() and file.stat().st_nlink == 1 and
                    file.stat().st_size <= 500000 and file.resolve().is_relative_to(root), 'Bounded local native schema required')
            schemas[name] = decode(file.read_bytes())
        contract = schema_contract(schemas)
    require(file_identity(binary.stat()) == epoch and hashlib.sha256(binary.read_bytes()).hexdigest() == expected_hash,
            'Native executable changed during schema export')
    return contract


def models(proxy):
    rows, hashes, cursor, seen, names = [], [], None, set(), set()
    for _ in range(8):
        page = proxy._rpc('model/list', {'cursor': cursor, 'limit': 30, 'includeHidden': False})
        require(isinstance(page, dict) and set(page) == {'data', 'nextCursor'} and isinstance(page['data'], list),
                'Complete bounded public model pages required')
        hashes.append(digest(page))
        for row in page['data']:
            require(isinstance(row, dict) and row.get('hidden') is False and isinstance(row.get('model'), str) and
                    0 < len(row['model']) <= 100 and isinstance(row.get('supportedReasoningEfforts'), list),
                    'Native advertised model/effort shape is unsupported')
            options = row['supportedReasoningEfforts']
            require(options and all(isinstance(v, dict) and isinstance(v.get('reasoningEffort'), str) for v in options),
                    'Missing reasoning effort observation is not zero')
            efforts = [v['reasoningEffort'] for v in options]
            require(len(efforts) == len(set(efforts)), 'Duplicate native effort observations')
            require(row['model'] not in names, 'Duplicate native model observation')
            names.add(row['model'])
            supported = [v for v in efforts if v in EFFORTS]
            # Report only the intersection with the existing standard protocol;
            # unsupported native values never become a guessed default.
            if supported:
                require(not any(v['model'] == row['model'] for v in rows), 'Duplicate native model observation')
                rows.append({'model': row['model'], 'efforts': supported})
            require(len(rows) <= 30, 'Public model catalog exceeds standard bound')
        cursor = page['nextCursor']
        if cursor is None:
            require(rows, 'No supported public model/effort combinations were observed')
            return rows, hashes
        require(isinstance(cursor, str) and 0 < len(cursor) <= 2048 and cursor not in seen, 'Incomplete or cyclic model pages')
        seen.add(cursor)
    require(False, 'Public model pagination is incomplete')


def identity(proxy, record, brain_id):
    project = proxy._rpc('project/read', {'projectId': record['projectId']}).get('project')
    thread = proxy._rpc('thread/read', {'threadId': brain_id, 'includeTurns': False}).get('thread')
    roots = project.get('roots') if isinstance(project, dict) else None
    require(isinstance(project, dict) and project.get('id') == record['projectId'] and
            isinstance(roots, list) and len(roots) == 1 and isinstance(roots[0], dict) and
            roots[0].get('path') == record['cwd'] and isinstance(thread, dict) and
            thread.get('id') == brain_id and thread.get('projectId') == record['projectId'] and
            thread.get('cwd') == record['cwd'] and thread.get('status', {}).get('type') == 'idle',
            'Exact already-loaded idle public brain and native project root required; no load fallback')
    require(not getattr(proxy, '_early_requests', []), 'Native permission/input remains unresolved')
    return {'brainId': brain_id, 'projectId': record['projectId'], 'checkout': record['cwd'],
            'catalogProjectId': record.get('catalogProjectId', record['projectId'])}


def environment(proxy, brain_id):
    value = proxy._rpc('mcpServerStatus/list', {'cursor': None, 'limit': 64,
                                             'detail': 'toolsAndAuthOnly', 'threadId': brain_id})
    require(value == {'data': [], 'nextCursor': None}, 'Public backend MCP inventory is not complete and empty')
    return digest(value)


def collect(proxy, binding, brain_id, command_id, handoff_hash):
    record = binding['brains'][brain_id]
    backend = validate_contract(record.get('nativeTaskBackend'), record.get('policyEvidence'))
    validate_endpoint(binding['endpoint'])
    schema = export_schemas(binding['endpoint']['executable'], binding['endpoint']['sha256'])
    from .native_auth_readiness import require_ready
    auth = require_ready(proxy)
    native_identity = identity(proxy, record, brain_id)
    native_environment = environment(proxy, brain_id)
    first, first_hashes = models(proxy)
    policy = policy_collect(proxy, binding, brain_id, command_id)
    require(matches(policy['reported']), 'Effective loaded native policy is unverified')
    second, second_hashes = models(proxy)
    require(first == second and first_hashes == second_hashes, 'Native model observations changed')
    require(identity(proxy, record, brain_id) == native_identity and environment(proxy, brain_id) == native_environment and
            require_ready(proxy)['responseHash'] == auth['responseHash'], 'Native public identity, environment or sign-in changed')
    validate_endpoint(binding['endpoint'])
    return {'version': VERSION, 'source': SOURCE, 'handoffHash': handoff_hash,
            'brainId': brain_id, 'commandId': command_id, 'bindingHash': digest(binding),
            'executableHash': binding['endpoint']['sha256'], 'backend': backend,
            'schema': schema, 'models': second, 'modelPageHashes': second_hashes,
            'identity': native_identity, 'environmentHash': native_environment, 'authenticationHash': auth['responseHash'],
            'policy': policy, 'observedAt': time.time(), 'boundary': dict(BOUNDARY)}


def validate(value, binding_hash, brain_id, command_id, handoff_hash):
    require(isinstance(value, dict) and set(value) == {'version', 'source', 'handoffHash', 'brainId',
        'commandId', 'bindingHash', 'executableHash', 'backend', 'schema', 'models', 'modelPageHashes',
        'identity', 'environmentHash', 'authenticationHash', 'policy', 'observedAt', 'boundary'} and
        type(value['version']) is int and value['version'] == VERSION and value['source'] == SOURCE and
        value['boundary'] == BOUNDARY and value['bindingHash'] == binding_hash and value['brainId'] == brain_id and
        value['commandId'] == command_id and value['handoffHash'] == handoff_hash,
        'Exact original public capability capture required')
    from .native_policy_evidence import EVIDENCE_FIELDS, PROTOCOL as POLICY_PROTOCOL
    require(isinstance(value['backend'], dict) and isinstance(value['schema'], dict) and
            set(value['schema']) == {'protocol', 'schemaHashes', 'methods', 'experimentalFields'} and
            isinstance(value['schema']['schemaHashes'], dict) and isinstance(value['policy'], dict) and
            set(value['policy']) == EVIDENCE_FIELDS and type(value['policy']['version']) is int and
            value['policy']['version'] == 1 and value['policy']['protocol'] == POLICY_PROTOCOL and
            isinstance(value['modelPageHashes'], list) and isinstance(value['identity'], dict),
            'Closed native capability evidence shapes required')
    validate_contract(value['backend'], {'protocol': 'loaded_thread_policy_v1',
        'sourceCommit': value['backend'].get('sourceCommit'), 'sourceTree': value['backend'].get('sourceTree')})
    require(value['schema'].get('protocol') == PROTOCOL and set(value['schema'].get('schemaHashes', {})) == set(SCHEMAS) and
            value['schema'].get('methods') == ['thread/start', 'turn/start'] and value['schema'].get('experimentalFields') is True and
            value['policy']['bindingHash'] == binding_hash and value['policy']['brainId'] == brain_id and
            value['policy']['commandId'] == command_id and matches(value['policy']['reported']) and
            value['policy']['executableHash'] == value['executableHash'] and
            all(value['backend'][k] == value['policy'][k] for k in ('sourceCommit', 'sourceTree')),
            'Model list alone is not public task-capability evidence')
    hashes = [value['bindingHash'], value['executableHash'], value['authenticationHash'], value['environmentHash'],
              value['policy']['responseHash'], value['handoffHash'],
              *value['schema']['schemaHashes'].values(), *value['modelPageHashes']]
    require(all(isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h) for h in hashes) and
            value['environmentHash'] == digest({'data': [], 'nextCursor': None}) and
            1 <= len(value['modelPageHashes']) <= 8 and value['identity'].get('brainId') == brain_id and
            set(value['identity']) == {'brainId', 'projectId', 'catalogProjectId', 'checkout'} and
            type(value['observedAt']) in (int, float) and math.isfinite(value['observedAt']) and
            0 < value['policy']['observedAt'] <= value['observedAt'] <= time.time(), 'Public evidence provenance is incomplete')
    require(isinstance(value['models'], list) and 1 <= len(value['models']) <= 30 and
            all(isinstance(row, dict) and set(row) == {'model', 'efforts'} and isinstance(row['model'], str) and
                0 < len(row['model']) <= 100 and isinstance(row['efforts'], list) and row['efforts'] and
                set(row['efforts']) <= EFFORTS and len(row['efforts']) == len(set(row['efforts'])) for row in value['models']) and
            len(value['models']) == len({r['model'] for r in value['models']}), 'Closed observed public model/effort subset required')
    return value


def retained_catalog(catalog, command, binding=None):
    """Cached provenance validation only; never collect or refresh a timestamp."""
    evidence = (catalog or {}).get('publicReadiness')
    note = (command or {}).get('notification') or {}
    require(evidence and command.get('status') == 'completed' and
            note.get('preplayCatalog', {}).get('version') == 2 and
            note.get('nativePublicReadinessHash') == digest(evidence) and
            note.get('nativeTaskContract') == evidence['backend'] and
            command.get('catalogReceipt', {}).get('catalogHash') == digest(catalog) and
            catalog['models'] == evidence['models'], 'Original public-backend catalog receipt required')
    validate(evidence, evidence['bindingHash'], note['brainId'], command['id'], note['preplayCatalog']['handoffHash'])
    profile = note.get('nativePublicReadinessProfile') or {}
    receipt = command.get('preplayReceipt') or {}
    require(profile.get('nativeLoadMade') is False and profile.get('bindingHash') == evidence['bindingHash'] and
            profile.get('commandId') == evidence['commandId'] and profile.get('brainId') == evidence['brainId'] and
            receipt.get('brainId') == evidence['brainId'] and receipt.get('handoffHash') == evidence['handoffHash'] and
            isinstance(receipt.get('requestHash'), str) and re.fullmatch('[0-9a-f]{64}', receipt['requestHash']) and
            isinstance(note.get('nativeTurnId'), str) and note['nativeTurnId'] and
            profile.get('nativeTurnId') == note.get('nativeTurnId') and
            command.get('preplayReceipt', {}).get('nativeTurnId') == note.get('nativeTurnId') and
            command['preplayReceipt']['bindingHash'] == evidence['bindingHash'], 'Original public loaded-only receipt identity required')
    if binding is not None:
        record = binding['brains'][evidence['brainId']]
        require(digest(binding) == evidence['bindingHash'] and binding['endpoint']['sha256'] == evidence['executableHash'] and
                record.get('nativeTaskBackend') == evidence['backend'] and record['cwd'] == evidence['identity']['checkout'] and
                record['projectId'] == evidence['identity']['projectId'] and
                record.get('catalogProjectId', record['projectId']) == evidence['identity']['catalogProjectId'],
                'Public task catalog belongs to another reviewed backend or binding')
    return evidence
