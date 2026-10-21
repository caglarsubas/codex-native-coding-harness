"""Real disposable native metadata after startup; no worker effect or reload."""
import time

from qualify_prestart_startup import Fixture as StartupFixture
from orchestrator import prestart_startup as startup, worker_readiness as worker
from orchestrator.core import require


class Fixture(StartupFixture):
    def run(self):
        setup = super().run()
        original = startup.databases(self.registry)
        protected = {**worker.inventory(self.q['request']['journal']),
                     **worker.inventory(self.q['request']['mailbox'])}
        destination = self.ledger.root.parent.parent / 'worker-readiness-evidence'
        result = worker.collect(self.registry, self.ledger,
                                self.q['request']['executionSource']['root'], destination)
        report = startup.mailbox.read(destination / 'report.json')
        activity = report['native']['activity']
        require(activity in ('idle', 'notLoaded'), 'Only actual inactive native metadata can be observed')
        if activity == 'notLoaded':
            require(report['native']['policy'] is None and report['native']['trackedTerminals'] is None and
                    'brain_not_loaded' in result['blockers'], 'Unloaded metadata cannot gain a load or inferred policy')
        else:
            require(worker.policy_matches(report['native']['policy']) and report['native']['trackedTerminals'] == [],
                    'Actually loaded metadata must retain the actual restricted policy and current tracker reads')
        require(startup.databases(self.registry) == original and all(startup.pin(p) == v for p, v in protected.items()),
                'Worker metadata observation changed an original database, claim or receipt')
        at = report['observedAt']
        saved = worker.status(self.registry, self.ledger, destination)
        require(saved['observedAt'] == at <= time.time() and saved['normalWritesBlocked'],
                'Status cannot renew observations or unfence writes')
        setup.update(workerReadinessStatus=result['status'], workerReadinessBlockers=result['blockers'],
            actualPostStartupActivity=activity,
            workerReadinessLoads=0, workerReadinessTurns=0, workerReadinessSubscriptions=0,
            workerReadinessProviderRequests=0, actualNativeSchemasExported=True,
            actualNativeModelChoices=len(report['models']), oldStartupReceiptAndUsageUnchanged=True,
            originalReadinessNotBackfilled=True, statusIsHistoricalAndNonAuthorizing=True)
        return setup
