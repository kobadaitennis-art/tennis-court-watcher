"""Deliver only confirmed vacancies, then acknowledge state. Retry-safe Issue marker."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from watcher import DATA, slot_key, build_notification


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def notification_marker(slots, state):
    events = sorted((slot_key(s), state['slots'][slot_key(s)].get('generation', 1)) for s in slots)
    return '<!-- tennis-vacancies:' + hashlib.sha256(json.dumps(events, ensure_ascii=False).encode()).hexdigest() + ' -->'


def health_event(result, state):
    """One alert after two failed observations; reset only on a complete success."""
    if result.get('mode') != 'katsushika_daily_v4' or result.get('skipped'):
        return None
    health = state.setdefault('katsushika_health', {'failures': 0, 'incident': 0})
    if health.get('last_check') != result['checked_at']:
        health['last_check'] = result['checked_at']
        if result['success']:
            health['failures'] = 0
            health['alerted'] = False
        else:
            if health['failures'] == 0:
                health['incident'] += 1
                health['alerted'] = False
            health['failures'] += 1
    if health['failures'] >= 2 and not health.get('alerted'):
        marker = f"<!-- tennis-health:katsushika:{health['incident']} -->"
        return marker
    return None


def main():
    result = json.loads((DATA/'latest.json').read_text(encoding='utf-8'))
    state = json.loads((DATA/'pending-state.json').read_text(encoding='utf-8'))
    if os.environ.get('DRY_RUN', 'false').lower() == 'true':
        print('Read-only validation: no Issue and no state acknowledgement.')
        return
    slots = result['new_or_reopened']
    alert = health_event(result, state)
    repo = os.environ['GH_REPO']
    if slots or alert:
        # Includes closed Issues so a closed notification is not repeated after a push failure.
        pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/issues?state=all&per_page=100'))
        previous_bodies = '\n'.join(issue.get('body') or '' for page in pages for issue in page if 'pull_request' not in issue)
    else:
        previous_bodies = ''
    if alert:
        if alert not in previous_bodies:
            body = DATA/'health-issue-body.md'
            errors = '\n'.join('- ' + e for e in result.get('errors', []))
            body.write_text(
                '葛飾区の空き状況を連続して完全取得できていません。\n'
                '未確認の枠は空きなしと判定せず、前回状態を保持しています。\n\n'
                + errors + '\n\n' + alert, encoding='utf-8')
            gh('issue', 'create', '--repo', repo, '--title', '⚠️ 葛飾区コート監視の取得異常',
               '--body-file', str(body), '--assignee', 'kobadaitennis-art')
        state['katsushika_health']['alerted'] = True
    if slots:
        unsent = [s for s in slots if notification_marker([s], state) not in previous_bodies]
        if unsent:
            body = DATA/'issue-body.md'
            markers = '\n'.join(notification_marker([s], state) for s in unsent)
            body.write_text(build_notification(unsent)+'\n\n'+markers, encoding='utf-8')
            gh('issue', 'create', '--repo', repo, '--title', f'🎾 テニスコート新規空き {len(unsent)}件',
               '--body-file', str(body), '--assignee', 'kobadaitennis-art')
        for s in slots:
            state['slots'][slot_key(s)]['notified'] = True
    else:
        print('No new vacancy Issue required.')
    (DATA/'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
