#!/usr/local/bin/python3

# you'll need to
# pip3 install beautifulsoup4
# pip3 install lxml
# git clone git@github.com:nik9000/compare_docs.git
# git clone git@github.com:elastic/docs.git
# git clone git@github.com:elastic/built-docs.git
# ./compare_docs/compare.py

from bs4 import BeautifulSoup
import collections
import datetime
import difflib
import os
import subprocess
import re

def run_git_command(dir, command):
    command = ['git'] + command
    process = subprocess.run(
            command,
            env = {
                'GIT_DIR': dir + '/.git',
                'GIT_WORK_TREE': dir,
            },
            stderr = subprocess.PIPE,
            stdout = subprocess.PIPE)
    if process.returncode != 0:
        raise Exception('Failed to run ' + str(command) + ' in ' + dir + ':' + str(process.stderr))
    return process.stdout.decode(encoding='utf-8', errors='strict')

def commit_date(dir, spec):
    as_str = run_git_command(dir, ['log', '-1', '--format=%ct', spec])
    return datetime.datetime.utcfromtimestamp(int(as_str))

def subject_of(dir, spec):
    return run_git_command(dir, ['log', '-1', '--format=%s', spec]).strip()

def hash_of(dir, spec):
    return run_git_command(dir, ['log', '-1', '--format=%h', spec]).strip()

def checkout(dir, spec):
    subprocess.run(['rm', '-f', dir + '/.git/index.lock'])
    run_git_command(dir, ['checkout', '-f', spec])

def paths_in(dir):
    result = []
    for path, dnames, fnames in os.walk(dir):
        path = path[len(dir) + 1:]
        for fname in fnames:
            result += ["%s/%s" % (path, fname)]
    return result

paths_that_have_differed = collections.deque(maxlen=10)
paths_that_have_differed.append('en/cloud/saas-release/index.html') # cheat the first diff for speed. temporary.
def compare_dirs(prefix, lhs, rhs):
    paths_in_lhs = set(paths_in(lhs))
    paths_in_rhs = set(paths_in(rhs))
    lhs_only = [item for item in paths_in_lhs if item not in paths_in_rhs]
    rhs_only = [item for item in paths_in_rhs if item not in paths_in_lhs]
    if len(lhs_only) > 0 or len(rhs_only) > 0:
        lhs_only.sort()
        rhs_only.sort()
        print("%s: File trees differed lhs=%s rhs=%s" % (prefix, str(lhs_only), str(rhs_only)))
        return False
    print("%s: Checking file contents" % prefix)
    checked = 0
    paths = [item for item in paths_that_have_differed if item in paths_in_lhs]
    paths += [item for item in paths_in_lhs if item not in paths_that_have_differed]
    for path in paths:
        if not path.endswith('.html'):
            # names matching is good enough for everything but html
            continue
        lhs_text = None
        rhs_text = None
        with open(lhs + '/' + path, encoding='utf-8') as lhs_file:
            lhs_text = lhs_file.read()
        with open(rhs + '/' + path, encoding='utf-8') as rhs_file:
            rhs_text = rhs_file.read()
        lhs_text = normalize_html(lhs_text)
        rhs_text = normalize_html(rhs_text)
        diff = difflib.unified_diff(lhs_text.splitlines(), rhs_text.splitlines(),
                fromfile = 'docs',
                tofile = 'built-docs',
                lineterm = '')
        diff = '\n'.join(diff)
        if diff:
            if path not in paths_that_have_differed:
                paths_that_have_differed.append(path)
            print("%s: File differs [%s]:\n%s" % (prefix, path, diff))
            return False
        checked += 1
        if checked % 100 == 0:
            print("%s: Checked [%05i] files" % (prefix, checked))
    print("%s: Full Match!" % prefix)

def normalize_html(html):
    # It looks like the render date can end up in the output
    # like 2019-01-14. I wonder if we can replace things that
    # look like that.
    html = re.sub(r'\d\d\d\d-\d\d-\d\d', '__a_date__', html)
    # Normalize the html so we can have more readable output
    # from the diff *and* to excuse any differences between
    # asciidoc and asciidoctor that shouldn't make a difference
    return BeautifulSoup(html, 'lxml').prettify()

docs_offset = 0
built_docs_offset = 0
docs_spec_prefix = 'master'
built_docs_spec_prefix = 'master'
while True:
    docs_spec = '%s~%s' % (docs_spec_prefix, docs_offset)
    built_docs_spec = '%s~%s' % (built_docs_spec_prefix, built_docs_offset)
    prefix = '%s/%s' % (hash_of('docs', docs_spec), hash_of('built-docs', built_docs_spec))
    docs_commit_date = commit_date('docs', docs_spec)
    built_docs_commit_date = commit_date('built-docs', built_docs_spec)
    docs_subject = subject_of('docs', docs_spec)
    built_docs_subject = subject_of('built-docs', built_docs_spec)
    if abs(docs_commit_date.timestamp() - built_docs_commit_date.timestamp()) >= 60 * 60 * 3:
        print("%s: Not within three hours [%s/%s]" % (prefix, docs_commit_date, built_docs_commit_date))
    elif docs_subject != 'Updated docs' or built_docs_subject != 'Updated docs':
        print("%s: Both are not docs updates [%s/%s]" % (prefix, docs_subject, built_docs_subject))
    else:
        print("%s: Checking file tree" % prefix)
        if docs_offset > 0:
            checkout('docs', docs_spec)
            docs_offset = 0
            docs_spec_prefix = 'HEAD'
        if built_docs_offset > 0:
            checkout('built-docs', built_docs_spec)
            built_docs_offset = 0
            built_docs_spec_prefix = 'HEAD'
        if compare_dirs(prefix, 'docs/html', 'built-docs/html'):
            break
    if docs_commit_date > built_docs_commit_date:
        docs_offset += 1
    else:
        built_docs_offset += 1