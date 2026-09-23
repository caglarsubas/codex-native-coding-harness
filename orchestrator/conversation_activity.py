"""Read-only, bounded project outcomes. Never imports a native transcript."""
import json
import re

from .core import digest

PR = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/[1-9][0-9]*", re.ASCII)


def pull_links(text):
    links = []
    for value in re.findall(r'https://[^\s<>\[\]()\"\']+', text):
        value = value.rstrip('.,;:')
        if PR.fullmatch(value) and value not in links:
            links.append(value)
    return links[:12]


def snapshot(db, meta):
    phases, seen = [], set()
    candidates = [(meta.get("standardRun"), None)]
    rows = db.execute("SELECT id,CASE WHEN length(data)<=1048576 THEN data END AS data FROM snapshots WHERE kind='standard_run' ORDER BY rowid DESC LIMIT 101").fetchall()
    issues = []
    for row in rows[:100]:
        if row['data'] is None:
            issues.append('An oversized phase record was omitted.'); continue
        try:
            doc = json.loads(row['data'])
            if digest(doc) != row['id']:
                raise ValueError('Changed phase record')
            candidates.append((doc['run'], doc.get('at')))
        except (ValueError, KeyError, TypeError):
            issues.append('An unreadable phase record was omitted.')
    for run, recorded_at in candidates:
        if not isinstance(run, dict) or run.get('id') in seen:
            continue
        seen.add(run.get('id'))
        if run.get('protocol') != 'standard_cooperative_v1' or run.get('brainId') != meta['brainId']:
            continue
        if len(phases) == 5:
            break
        tasks = []
        for task in run.get('tasks', [])[:30]:
            item = {key: task.get(key) for key in ('id', 'title', 'repository', 'status', 'finishedAt', 'result')}
            item.update(evidence=None, pullRequests=[], issue=None)
            if task.get('result'):
                row = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='standard_result' AND length(data)<=65536", (task['result'],)).fetchone()
                try:
                    if not row or len(row[0]) > 65536:
                        raise ValueError('Missing result')
                    doc = json.loads(row[0])
                    if digest(doc) != task['result'] or doc['runId'] != run['id'] or doc['taskId'] != task['id']:
                        raise ValueError('Result identity mismatch')
                    evidence = {k: doc['evidence'][k] for k in ('summary', 'source', 'tests', 'preservation')}
                    if not all(isinstance(v, str) and len(v) <= 8000 for v in evidence.values()):
                        raise ValueError('Invalid evidence')
                    item['evidence'] = evidence
                    observation = db.execute("SELECT data FROM observation_records WHERE id=? AND length(data)<=1048576", ('git:' + task['repository'],)).fetchone()
                    observed = json.loads(observation[0]) if observation and len(observation[0]) <= 1_048_576 else {}
                    remote = observed if observed.get('remoteAt') else observed.get('previousRemote') or {}
                    for url in pull_links('\n'.join(evidence.values())):
                        match = next((p for p in remote.get('pullRequests', []) if p.get('url') == url), {})
                        item['pullRequests'].append({'url': url, 'state': match.get('state', 'unknown'),
                            'observedAt': remote.get('remoteAt') if match else None,
                            'refreshStatus': observed.get('remoteStatus', 'not_requested')})
                except (ValueError, KeyError, TypeError):
                    item.update(evidence=None, pullRequests=[], issue='Retained result unavailable or changed; inspect Workers & evidence.')
            tasks.append(item)
        phases.append({'id': run['id'], 'phaseId': run.get('phaseId'), 'status': run.get('status'),
            'at': (run.get('checkpoint') or {}).get('at') or recorded_at or run.get('updatedAt') or run.get('createdAt'),
            'checkpoint': (run.get('checkpoint') or {}).get('summary'), 'tasks': tasks})
    return {'phases': phases, 'issues': sorted(set(issues)),
        'limited': len(rows) > 100 or len(seen) > 5,
        'boundary': 'Latest five retained cooperative phases from at most 100 versions. Recorded outcomes, not a full Codex transcript or live GitHub status.'}
