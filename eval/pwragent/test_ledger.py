import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from ledger import Ledger, ledger_paths


class BudgetTests(unittest.TestCase):
    def test_fresh_stage_does_not_charge_or_change_previous_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            old=Ledger(ledger_paths(d,{})[0],500)
            old.reserve('historical',400)
            fresh=Ledger(ledger_paths(d,{'budget_ledger':'stage5-ledger'})[0],500)
            fresh.reserve('new',100)
            self.assertEqual(old.snapshot()['remaining_usd'],100)
            self.assertEqual(fresh.snapshot()['remaining_usd'],400)
            with self.assertRaises(ValueError): ledger_paths(d,{'budget_ledger':'../escape'})

    def test_review_pause_blocks_before_any_model_admission(self):
        import run_stage
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'PAUSED_FOR_REVIEW.json').write_text('{}')
            with patch.object(run_stage,'LOCAL',root):
                with self.assertRaisesRegex(RuntimeError,'explicit user review'):
                    run_stage.execute(SimpleNamespace(limit=None,retry_infra=None))

    def test_resume_and_uncertain_spend_cannot_release_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'ledger.sqlite'
            a = Ledger(path, 10)
            a.reserve('one', 7)
            b = Ledger(path, 10)
            with self.assertRaises(ValueError): b.reserve('two', 4)
            with self.assertRaises(ValueError): b.reserve('one', 1)
            b.settle('one', 0, uncertain=True)
            self.assertEqual(a.snapshot()['remaining_usd'], 3)
            with self.assertRaises(ValueError): a.reserve('three', 4)

    def test_settlement_releases_only_known_unused_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            a = Ledger(Path(d)/'ledger.sqlite', 10)
            a.reserve('one', 7)
            with self.assertRaises(ValueError): a.settle('one', 8)
            a.settle('one', 2)
            a.reserve('two', 8)
            self.assertEqual(a.snapshot()['remaining_usd'], 0)

    def test_reconciliation_requires_uncertain_status_and_keeps_audit(self):
        with tempfile.TemporaryDirectory() as d:
            a=Ledger(Path(d)/'ledger.sqlite',10)
            a.reserve('one',7);a.settle('one',0,uncertain=True)
            with self.assertRaises(ValueError):a.reconcile('one',8,'counter proof')
            a.reconcile('one',2,'matching terminal + provider counters')
            self.assertEqual(a.snapshot()['remaining_usd'],8)
            self.assertEqual(a.snapshot()['reconciliations'][0]['prior_charge_micros'],7_000_000)
            with self.assertRaises(ValueError):a.reconcile('one',0,'second mutation')


if __name__ == '__main__': unittest.main()
