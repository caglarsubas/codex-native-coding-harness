"""Closed authenticated recovery view. No WorkspaceRuntime, notifier or writer.

Browser pairing is isolated in the new reviewed view directory. All operational
POSTs and alternate write methods are denied before any operational code runs.
"""
from http.server import ThreadingHTTPServer
import secrets
import time
from urllib.parse import urlsplit

from . import post_reboot_dashboard as control
from .browser_auth import BrowserAuth
from .core import Refusal, require
from .server import Handler as SecurityHeaders
from .standard_quarantine import exclusive


def projection(q, observed):
    require(q['sourceHash'] == control.source_hash(), 'Dashboard source changed')
    require(all(control.pin(v['path']) == v for v in q['evidencePins'].values()), 'Reviewed evidence changed')
    c, _, _, _ = control.foundation(q['repairFile'], q['launchedSource'])
    require(c == q['context'], 'Certificate scope changed; recovery view unavailable')
    usage = c['originalUsage']
    # A closed projection, not Ledger.snapshot(), mission eligibility or native
    # polling. Never expose SQL rows, old prompt bodies, paths or credentials.
    return {'mode': 'certificate_read_only', 'workspaceId': c['workspaceId'], 'brainId': c['brainId'],
        'status': 'Preparation retained; pilot not started', 'paused': True, 'registeredTasks': 0,
        'originalReadiness': {'id': c['originalReadinessId'], 'status': 'unqualified_preserved'},
        'preparation': {'latestTurnId': c['latestTurnId'], 'turnStatus': 'completed',
                        'historicalObservedAt': c['historicalObservedAt']},
        'usage': {k: usage[k] for k in ('observedLastTurnTokens', 'chargedReservationFloor',
                  'carriedPhaseCeiling', 'futurePhaseCeiling', 'coverage', 'gaps')},
        'connection': {'pid': c['pid'], 'observedAt': observed['observedAt'],
            'activityAtObservation': observed['observation']['activity'],
            'loadedPolicyMatchedAtObservation': control.policy.matches(observed['observation']['policy']),
            'policyVerified': False,
            'observationStale': not 0 <= time.time() - observed['observedAt'] < 300,
            'savedSignInPresentAtObservation': observed['authentication']['accountPresent'],
            'authenticationReadyAtObservation': observed['authentication']['ready'],
            'nativeMetadataFreshlyCollected': False, 'modelAccessVerified': False},
        'nextStep': 'A separately qualified worker-readiness and execution path is still required. This view grants no load or Play.',
        'boundary': dict(control.BOUNDARY)}


class RecoveryDashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, review, observation, directory):
        super().__init__(('127.0.0.1', review['port']), RecoveryHandler)
        self.review, self.observation = review, observation
        self.origin = 'http://127.0.0.1:' + str(self.server_port)
        self.account = None; self.bootstrap = secrets.token_urlsafe(32)
        try:
            self.browser_auth = BrowserAuth(directory, self.origin)
            exclusive(directory / 'dashboard-session.json', {'url': self.origin + '/#token=' + self.bootstrap,
                'workspaceId': review['context']['workspaceId'], 'mode': 'certificate_read_only'})
        except BaseException:
            self.server_close(); raise

    def get_request(self):
        connection, address = super().get_request(); connection.settimeout(5)
        return connection, address

    def handle_error(self, *_):
        pass  # No private scope, authentication or native diagnostics in HTTP logs.


class RecoveryHandler(SecurityHeaders):
    def blocked(self):
        return self.respond(405, {'error': 'Read-only recovery workspace: operational controls are unavailable',
                                  'boundary': control.BOUNDARY}, headers={'Allow': 'GET'})

    def do_GET(self):
        if not self.host_ok(): return self.respond(403, {'error': 'Host refused'})
        parsed = urlsplit(self.path)
        if parsed.query: return self.respond(400, {'error': 'Query parameters are not supported'})
        path = parsed.path
        static = {'/': ('maintenance.html', 'text/html; charset=utf-8'),
                  '/maintenance.js': ('maintenance.js', 'text/javascript; charset=utf-8'),
                  '/maintenance.css': ('maintenance.css', 'text/css; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in static:
            name, mime = static[path]
            try:
                require(self.server.review['sourceHash'] == control.source_hash(), 'Recovery source changed')
                return self.respond(200, control.asset(name), mime)
            except (Refusal, OSError, ValueError, KeyError, TypeError):
                return self.respond(503, {'error': 'Recovery source changed; no unreviewed asset is served'})
        if path == '/healthz': return self.respond(200, {'status': 'ok', 'mode': 'certificate_read_only'})
        if path == '/api/auth/options': return self.respond(200, {'mode': 'private-link'})
        try:
            session = self.session()
            if not session: return self.respond(401, {'error': 'Connect using this recovery dashboard’s private link', 'authRequired': True})
            if path == '/api/session': return self.respond(200, self.server.browser_auth.public(session))
            workspace = self.server.review['context']['workspaceId']
            if path in ('/api/state', '/api/workspaces/' + workspace + '/state'):
                return self.respond(200, projection(self.server.review, self.server.observation))
            return self.respond(404, {'error': 'Unavailable in the selected read-only workspace'})
        except (Refusal, OSError, ValueError, KeyError, TypeError):
            return self.respond(503, {'error': 'Recovery scope changed or is unavailable. No operation was sent.'})

    def do_POST(self):
        # These are the only local browser-auth mutations, isolated from every
        # operational store. Inherited code returns before operational routing.
        if self.path not in ('/api/login', '/api/logout', '/api/session/remember'):
            return self.blocked()
        return super().do_POST()

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = blocked
