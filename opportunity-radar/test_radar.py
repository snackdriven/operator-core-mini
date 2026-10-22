import copy
import json
import unittest
from pathlib import Path

from radar import evaluate


class RadarTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(
            Path(__file__).with_name('fixture.json').read_text(encoding='utf-8'))

    def test_verified_available_exceptional_event_surfaces(self):
        result = evaluate(self.snapshot)
        self.assertEqual(len(result['findings']), 1)
        self.assertIn('evidence', result['findings'][0])
        self.assertEqual(evaluate({**self.snapshot,
            'previous': result['nextCheckpoint']})['findings'], [])

    def test_missing_calendar_or_travel_coverage_is_unknown(self):
        for change in ('missing', 'partial', 'buffer'):
            snapshot = copy.deepcopy(self.snapshot)
            if change == 'missing':
                snapshot['calendars'] = []
            elif change == 'partial':
                snapshot['calendars'][0]['coverage'] = 'partial'
            else:
                snapshot['calendars'][0]['start'] = snapshot['candidates'][0]['start']
            result = evaluate(snapshot)
            self.assertEqual(result['findings'], [])
            self.assertEqual(len(result['unknown']), 1)
            self.assertEqual(result['nextCheckpoint'], {})

    def test_conflict_stale_tickets_and_revoked_consent(self):
        for change in ('busy', 'stale', 'consent', 'sold-out', 'ordinary', 'future'):
            snapshot = copy.deepcopy(self.snapshot)
            candidate = snapshot['candidates'][0]
            if change == 'busy':
                snapshot['calendars'][0]['busy'] = [{
                    'start': candidate['start'], 'end': candidate['end']}]
            elif change == 'stale':
                candidate['ticketEvidence']['observedAt'] = '2026-09-29T15:00:00Z'
            elif change == 'consent':
                snapshot['consent']['sources'] = []
            elif change == 'sold-out':
                candidate['tickets'] = 'sold-out'
            elif change == 'ordinary':
                candidate['score'] = 40
            else:
                candidate['eventEvidence']['observedAt'] = '2026-10-01T15:00:00Z'
            self.assertEqual(evaluate(snapshot)['findings'], [], change)

    def test_invalid_interval_and_conflicting_identity_fail_loud(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['candidates'][0]['end'] = snapshot['candidates'][0]['start']
        with self.assertRaises(ValueError):
            evaluate(snapshot)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['candidates'].append(copy.deepcopy(snapshot['candidates'][0]))
        with self.assertRaises(ValueError):
            evaluate(snapshot)


if __name__ == '__main__':
    unittest.main()
