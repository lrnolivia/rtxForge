#!/usr/bin/env python3
"""Check commit identity and unsolicited tool credits without scanning product text."""
import argparse, json, pathlib, re, subprocess, sys

IDENTITY = re.compile(r'(?i)(?:^(?:Codex|Claude(?: Code)?|ChatGPT|OpenAI|relay-by-loew-fi\[bot\]|dot\[bot\])\s*<|<codex@openai\.com>|<[^>]*(?:relay-by-loew-fi\[bot\]|claude\[bot\]|chatgpt\[bot\]|dot\[bot\])[^>]*>)')
CREDIT = re.compile(r'(?im)^\s*(?:co-authored-by|generated[- ]by|written[- ]by|authored[- ]by|agent[- ]session)\s*:\s*[^\n]*(?:\bCodex\b|\bClaude\b|\bChatGPT\b|\bOpenAI\b|relay-by-loew-fi|\bdot\[bot\])')
ADVERTISING = re.compile(r'(?im)^\s*(?:🤖\s*)?(?:generated|written|authored)\s+(?:with|by|using)\s+[^\n]*(?:\bCodex\b|\bClaude\b|\bChatGPT\b|\bOpenAI\b|\bRelay\b)')

def violations(author, committer, message):
    problems=[]
    for label,value in [('author',author),('committer',committer)]:
        if value and IDENTITY.search(value): problems.append(label+' uses a tool identity')
    if CREDIT.search(message) or ADVERTISING.search(message): problems.append('message contains an unsolicited tool credit')
    return problems

def push_base(repo, head, event):
    before = event.get('before')
    if not before:
        return None
    if before != '0' * 40:
        return before
    default_branch = event['repository']['default_branch']
    if event['ref'] == f'refs/heads/{default_branch}':
        return None
    return subprocess.check_output(
        ['git', '-C', repo, 'merge-base', head, f'refs/remotes/origin/{default_branch}'],
        text=True,
    ).strip()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--repo',default='.');p.add_argument('--head',default='HEAD');p.add_argument('--base');p.add_argument('--event');p.add_argument('--message-file');p.add_argument('--author');p.add_argument('--committer');a=p.parse_args()
    errors=[]
    if a.message_file:
        errors.extend(violations(a.author,a.committer,pathlib.Path(a.message_file).read_text()))
    else:
        event = json.loads(pathlib.Path(a.event).read_text()) if a.event else {}
        base = a.base or push_base(a.repo, a.head, event)
        target = f'{base}..{a.head}' if base else a.head
        commits=subprocess.check_output(['git','-C',a.repo,'rev-list',target],text=True).splitlines()
        for sha in commits:
            raw=subprocess.check_output(['git','-C',a.repo,'cat-file','commit',sha],text=True);headers,msg=raw.split('\n\n',1)
            author=next(x[7:] for x in headers.splitlines() if x.startswith('author '));committer=next(x[10:] for x in headers.splitlines() if x.startswith('committer '))
            errors.extend(sha+': '+x for x in violations(author,committer,msg))
        if pr := event.get('pull_request'):
            errors.extend('PR squash text: '+x for x in violations(None,None,pr.get('title','')+'\n'+(pr.get('body') or '')))
    if errors:print('\n'.join(errors),file=sys.stderr);return 1
    print('Attribution policy passed');return 0

if __name__=='__main__':sys.exit(main())
