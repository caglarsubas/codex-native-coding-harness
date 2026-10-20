"""Real disposable SQLite transitions; no native connection, model or live files."""
import copy
import json
import sqlite3
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import admission_continuity as api, empty_setup_transition as setup, missions, standard
from orchestrator.core import Ledger, Refusal, canonical, digest
from test_empty_setup_transition import Fixture


class ContinuityTest(Fixture):
    def setUp(self):
        super().setUp()
        self.preview_value=self.preview(); self.receipt=self.confirm(self.preview_value)
        self.source=self.registry.ledger('old')

    def validate(self): return api.validate(self.registry,self.source,'target')

    def test_completed_transition_is_read_only_with_unchanged_old_rows_and_unknown_safety(self):
        calls=list(self.calls); before={p:self.contents(p) for p in (self.registry.db,self.ledger.db,self.source.db)}
        with patch.object(setup,'observe',side_effect=AssertionError('No native collection')):
            value=self.validate(); self.assertEqual(value,self.validate())
        self.assertEqual(self.calls,calls); self.assertEqual(len(value['snapshots']),3)
        self.assertEqual(before,{p:self.contents(p) for p in before})
        self.assertEqual(self.receipt['boundary'],setup.BOUNDARY)

    def test_original_registry_backup_anchors_only_exact_causal_changes(self):
        value=self.validate(); snapshot=value['snapshots'][str(self.registry.db)]
        old={'databases':{'registry':{'identity':[self.registry.db.stat().st_dev,self.registry.db.stat().st_ino],
            'fingerprint':api.partial_admission.database_proof(snapshot['path'])['fingerprint']}},
            'scope':{'catalogHash':self.preview_value['request']['oldCatalog']['hash']},'usage':101877}
        current=copy.deepcopy(old); current['databases']['registry']=api.partial_admission.database_proof(self.registry.db)
        with setup.read_database(self.registry.db) as db: catalog,_=api.projects._read(db)
        current['scope']['catalogHash']=catalog['hash']
        self.assertEqual(api.original_relation(self.registry,self.source,old,current,'target'),value)
        current['usage']=0
        with self.assertRaises(Refusal): api.original_relation(self.registry,self.source,old,current,'target')

    def test_later_mission_review_does_not_expire_historical_continuity(self):
        before=self.validate(); target=self.registry.ledger('target'); state=missions.read(target)
        missions.change(target,{'id':'review-once','operation':'review','expectedRevision':state['revision'],
            'documentHash':state['documentHash'],'confirmed':True})
        self.assertEqual(before,self.validate())

    def test_later_normal_target_append_does_not_mutate_predecessor_proof(self):
        before=self.validate(); target=self.registry.ledger('target')
        with target.tx() as db:
            meta=Ledger.get(db,'meta',1); meta.update(revision=meta['revision']+1,paused=False)
            Ledger.put(db,'meta',1,meta); target.event(db,'fixture_later_forward_control',{'noNativeCall':True})
        self.assertEqual(before,self.validate())

    def test_missing_or_partial_receipt_refuses_without_native_fallback(self):
        (self.ledger.root/setup.RECEIPT).unlink()
        with self.assertRaises(Refusal): self.validate()

    def test_changed_canonical_claim_refuses(self):
        self.write(self.ledger.root/setup.FENCE,{'kind':setup.KIND,'reviewHash':'0'*64,'at':1})
        with self.assertRaises(Refusal): self.validate()

    def test_source_ledger_counter_or_claim_change_refuses(self):
        with self.source.tx() as db:
            meta=Ledger.get(db,'meta',1); meta['oldUsage']['tokens']=0; Ledger.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): self.validate()

    def test_unrelated_registry_row_change_refuses(self):
        with self.registry.tx() as db: db.execute("UPDATE workspaces SET name='Changed' WHERE id='old'")
        with self.assertRaises(Refusal): self.validate()

    def test_unrelated_schema_change_refuses(self):
        with self.registry.tx() as db: db.execute('CREATE TABLE extra_owner(id TEXT)')
        with self.assertRaises(Refusal): self.validate()

    def test_changed_old_target_snapshot_refuses(self):
        with self.registry.ledger('target').tx() as db:
            db.execute('UPDATE snapshots SET data=? WHERE id=?',('{}',self.preview_value['request']['draftHash']))
        with self.assertRaises(Refusal): self.validate()

    def test_new_target_repository_or_brain_substitution_refuses(self):
        with self.registry.ledger('target').tx() as db:
            row=Ledger.all(db,'repos')[0]; row['projectId']='substitute'; Ledger.put(db,'repos',row['id'],row)
        with self.assertRaises(Refusal): self.validate()

    def test_backups_missing_or_changed_cannot_be_owner_authored_evidence(self):
        value=self.validate(); path=Path(value['snapshots'][str(self.source.db)]['path'])
        path.write_bytes(b'not a database')
        with self.assertRaises((Refusal,sqlite3.DatabaseError)): self.validate()

    def test_manifest_cannot_drop_old_database(self):
        root=self.registry.root/'backups'/self.receipt['backupId']; value=setup.read(root/'manifest.json')
        value['databases'].pop(); self.write(root/'manifest.json',value)
        with self.assertRaises(Refusal): self.validate()

    def test_manifest_cannot_retarget_backup_path(self):
        root=self.registry.root/'backups'/self.receipt['backupId']; value=setup.read(root/'manifest.json')
        value['databases'][0]['copy']='../unreviewed.sqlite3'; self.write(root/'manifest.json',value)
        with self.assertRaises(Refusal): self.validate()

    def test_original_consumed_setup_input_epoch_drift_refuses(self):
        path=Path(self.spec['setupRecords']['brainClaim']); raw=path.read_bytes(); path.write_bytes(raw)
        with self.assertRaises(Refusal): self.validate()

    def test_original_config_append_is_not_policy_or_configuration_bypass(self):
        with self.config.open('a') as out: out.write('\nadditional_unreviewed = true\n')
        with self.assertRaises(Refusal): self.validate()

    def test_unknown_historical_implementation_refuses(self):
        with self.assertRaises(Refusal): api.implementation('0'*64,self.root,api.PR184_SOURCE)
        with patch.object(api,'source_proof',return_value={'sourceHash':'0'*64}):
            with self.assertRaises(Refusal): api.implementation(api.PR184_SOURCE,self.root,api.PR184_SOURCE)

    def test_original_record_catalog_hash_cannot_be_fabricated(self):
        value=self.validate(); snapshot=value['snapshots'][str(self.registry.db)]
        old={'databases':{'registry':{'identity':[self.registry.db.stat().st_dev,self.registry.db.stat().st_ino],
            'fingerprint':api.partial_admission.database_proof(snapshot['path'])['fingerprint']}},
            'scope':{'catalogHash':'0'*64}}
        current=copy.deepcopy(old); current['databases']['registry']=api.partial_admission.database_proof(self.registry.db)
        with self.assertRaises(Refusal): api.original_relation(self.registry,self.source,old,current,'target')


if __name__=='__main__': unittest.main()
