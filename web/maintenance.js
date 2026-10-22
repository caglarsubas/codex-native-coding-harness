'use strict';
(function () {
  let state = null, selected = 'brain';
  const byId = id => document.getElementById(id);
  function notice(text, error = false) {
    byId('notice').textContent = text; byId('notice').dataset.error = String(error);
  }
  function rows(target, values) {
    const root = byId(target); root.replaceChildren();
    for (const [name, value] of values) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = name; dd.textContent = String(value); root.append(dt, dd);
    }
  }
  function date(value) { return Number.isFinite(value) ? new Date(value * 1000).toLocaleString() : 'Not observed'; }
  function amount(value) { return Number.isFinite(value) ? value.toLocaleString() : 'Unknown'; }
  function render() {
    const c = state.connection, brain = selected === 'brain';
    byId('workspace').hidden = false;
    byId('project').textContent = state.workspaceId;
    byId('next-step').textContent = state.nextStep;
    byId('brain-status').textContent = c.activityAtObservation === 'notLoaded' ? 'Unloaded at last check · policy unknown' : 'Idle at last check · not a safety finding';
    byId('brain-node').setAttribute('aria-pressed', String(brain));
    byId('preparation-node').setAttribute('aria-pressed', String(!brain));
    byId('inspector-title').textContent = brain ? 'Designated brain' : 'Retained preparation';
    byId('inspector-summary').textContent = brain
      ? 'The native connection was checked without loading the brain. This saved observation is not a live subscription.'
      : 'The separate preparation completed and retained its proposal. The earlier readiness request remains unqualified; neither request can be replayed.';
    rows('facts', brain ? [
      ['Activity at observation', c.activityAtObservation], ['Native metadata observed', date(c.observedAt)],
      ['Saved sign-in at observation', c.savedSignInPresentAtObservation ? 'Present; model access unverified' : 'Not present'],
      ['Loaded policy', c.loadedPolicyMatchedAtObservation ? 'Matched at observation; not current policy or safety' : 'Unknown'],
      ['Observation freshness', c.observationStale ? 'Stale; no automatic refresh' : 'Saved check only; not live activity'],
      ['Current / historical terminal safety', 'Unknown / unknown']
    ] : [['Preparation turn', state.preparation.latestTurnId], ['Recorded turn outcome', 'Completed; no pilot acceptance'],
      ['Original historical observation', date(state.preparation.historicalObservedAt)], ['Requests and consumed claims', 'Preserved unchanged']]);
    rows('usage', [['Observed preparation tokens', amount(state.usage.observedLastTurnTokens)],
      ['Charged reservation or larger overrun', amount(state.usage.chargedReservationFloor)],
      ['Original carried ceiling', amount(state.usage.carriedPhaseCeiling)],
      ['Recorded future ceiling — not authority', amount(state.usage.futurePhaseCeiling)],
      ['Coverage', state.usage.coverage], ['Preserved gaps', state.usage.gaps.join(', ')]]);
    byId('request').textContent = 'Original readiness ' + state.originalReadiness.id + ': unqualified, preserved. No receipt was reconstructed.';
    notice('Read-only recovery view · no reload, replay or automatic execution');
  }
  async function refresh() {
    try {
      const response = await fetch('/api/state', {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error(response.status === 401
        ? 'Connect this browser using the current private recovery-dashboard link.'
        : 'Recovery scope is unavailable or changed. No operation was sent.');
      const next = await response.json();
      if (next.mode !== 'certificate_read_only') throw new Error('Unexpected recovery view. No operation was sent.');
      state = next; render();
    } catch (error) { byId('workspace').hidden = true; notice(error.message, true); }
  }
  for (const [id, value] of [['brain-node', 'brain'], ['preparation-node', 'preparation']]) {
    byId(id).addEventListener('click', () => { selected = value; if (state) render(); });
  }
  byId('refresh').addEventListener('click', refresh);
  byId('theme').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    try { localStorage.setItem('orchestrator-recovery-theme', dark ? 'dark' : 'light'); } catch (_) { /* Optional local preference. */ }
  });
  async function start() {
    try { document.documentElement.dataset.theme = localStorage.getItem('orchestrator-recovery-theme') || 'light'; } catch (_) { /* Optional. */ }
    const fragment = new URLSearchParams(location.hash.slice(1)), token = fragment.get('token');
    if (token) {
      history.replaceState(null, '', location.pathname);
      try {
        const response = await fetch('/api/login', {method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token})});
        if (!response.ok) throw new Error('This private recovery link could not connect the browser.');
      } catch (error) { notice(error.message, true); return; }
    }
    await refresh();
  }
  start();
})();
