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


def main():
    result = json.loads((DATA/'latest.json').read_text(encoding='utf-8'))
    state = json.loads((DATA/'pending-state.json').read_text(encoding='utf-8'))
    if os.environ.get('DRY_RUN', 'false').lower() == 'true':
        print('Read-only validation: no Issue and no state acknowledgement.')
        return
    slots = result['new_or_reopened']
    if slots:
        repo = os.environ['GH_REPO']
        # Includes closed Issues so a closed notification is not repeated after a push failure.
        pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/issues?state=all&per_page=100'))
        previous_bodies = '\n'.join(issue.get('body') or '' for page in pages for issue in page if 'pull_request' not in issue)
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
        print('No new vacancies; no Issue created.')
    (DATA/'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
