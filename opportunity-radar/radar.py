"""Pure snapshot projection; no collector, personal-state writer, or sender."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamps require an explicit UTC offset')
    return parsed


def interval(record):
    start, end = instant(record['start']), instant(record['end'])
    if end <= start:
        raise ValueError('interval end must be after start')
    return start, end


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('expected nonempty text')
    return value


def number(value, minimum=0, maximum=float('inf')):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('expected a number')
    if not minimum <= value <= maximum:
        raise ValueError('number outside permitted range')
    return value


def fresh(evidence, now, max_age):
    text(evidence['source'])
    text(evidence['sourceRef'])
    age = (now - instant(evidence['observedAt'])).total_seconds()
    return 0 <= age <= max_age


def evaluate(snapshot):
    if snapshot['schema'] != 'opportunity-radar-input/v1':
        raise ValueError('unsupported snapshot schema')
    now = instant(snapshot['now'])
    config = snapshot['config']
    max_age = number(config['maxAgeSeconds'], 1)
    min_score = number(config['minScore'], 0, 100)
    max_price = number(config['maxPrice'])
    currency = text(config['currency'])
    buffer = timedelta(minutes=number(config['travelBufferMinutes']))
    required = config['requiredCalendars']
    if not isinstance(required, list) or not required:
        raise ValueError('at least one authoritative calendar is required')
    if len(set(required)) != len(required):
        raise ValueError('duplicate required calendar')
    for calendar_id in required:
        text(calendar_id)
    consent = snapshot['consent']
    text(consent['policyRef'])
    if not isinstance(consent['sources'], list):
        raise ValueError('consent sources must be a list')
    consent_current = instant(consent['observedAt']) <= now < instant(consent['expiresAt'])
    consent_current = consent_current and (now - instant(consent['observedAt'])).total_seconds() <= max_age
    calendars = {}
    for calendar in snapshot['calendars']:
        calendar_id = text(calendar['id'])
        if calendar_id in calendars:
            raise ValueError('duplicate calendar identity')
        interval(calendar)
        if calendar['coverage'] not in ('complete', 'partial', 'unknown'):
            raise ValueError('invalid calendar coverage')
        fresh(calendar['evidence'], now, max_age)
        for busy in calendar['busy']:
            interval(busy)
        calendars[calendar_id] = calendar
    previous = snapshot['previous']
    if not isinstance(previous, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in previous.items()):
        raise ValueError('previous must map candidate IDs to fingerprints')
    next_checkpoint = dict(previous)
    findings, unknown, suppressed = [], [], []
    candidate_ids = set()
    for candidate in snapshot['candidates']:
        key = text(candidate['id'])
        if key in candidate_ids:
            raise ValueError('duplicate candidate identity; reconcile at source')
        candidate_ids.add(key)
        text(candidate['title'])
        start, end = interval(candidate)
        price = number(candidate['price'])
        score = number(candidate['score'], 0, 100)
        text(candidate['currency'])
        if not isinstance(candidate['reasons'], list):
            raise ValueError('reasons must be a list')
        for reason in candidate['reasons']:
            text(reason)
        if candidate['tickets'] not in ('available', 'sold-out', 'unknown'):
            raise ValueError('invalid ticket status')
        event_fresh = fresh(candidate['eventEvidence'], now, max_age)
        ticket_fresh = fresh(candidate['ticketEvidence'], now, max_age)
        sources = {candidate['eventEvidence']['source'], candidate['ticketEvidence']['source']}
        sources.update(calendars[c]['evidence']['source'] for c in required if c in calendars)
        if not consent_current or not sources.issubset(set(consent['sources'])):
            unknown.append({'id': key, 'reason': 'Missing or expired source consent.'})
            continue
        if not event_fresh or not ticket_fresh or candidate['tickets'] == 'unknown':
            unknown.append({'id': key, 'reason': 'Event or ticket evidence is not current.'})
            continue
        window_start, window_end = start - buffer, end + buffer
        coverage_known = all(c in calendars and calendars[c]['coverage'] == 'complete'
            and fresh(calendars[c]['evidence'], now, max_age)
            and interval(calendars[c])[0] <= window_start
            and interval(calendars[c])[1] >= window_end for c in required)
        if not coverage_known:
            unknown.append({'id': key, 'reason': 'Calendar coverage does not prove availability.'})
            continue
        busy = any(interval(slot)[0] < window_end and interval(slot)[1] > window_start
            for c in required for slot in calendars[c]['busy'])
        eligible = (start > now and candidate['tickets'] == 'available' and not busy
            and score >= min_score and bool(candidate['reasons']) and price <= max_price
            and candidate['currency'] == currency)
        if not eligible:
            suppressed.append({'id': key, 'reason': 'Outside criteria or unavailable.'})
            continue
        material = {k: v for k, v in candidate.items()
            if k not in ('eventEvidence', 'ticketEvidence')}
        material['sources'] = sorted(sources)
        material['sourceRefs'] = [candidate['eventEvidence']['sourceRef'],
            candidate['ticketEvidence']['sourceRef']]
        fp = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        if previous.get(key) != fp:
            findings.append({'id': key, 'title': candidate['title'],
                'reasons': candidate['reasons'], 'start': candidate['start'],
                'price': price, 'currency': currency, 'availability': 'free-at-observation',
                'evidence': {'event': candidate['eventEvidence'],
                    'tickets': candidate['ticketEvidence'],
                    'calendars': [calendars[c]['evidence'] for c in required],
                    'consentPolicyRef': consent['policyRef']}})
        next_checkpoint[key] = fp
    return {'schema': 'opportunity-radar-evaluation/v1', 'generatedAt': snapshot['now'],
        'findings': findings, 'unknown': unknown, 'suppressed': suppressed,
        'nextCheckpoint': next_checkpoint}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.file.read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'error: {args.file}: {error}\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
