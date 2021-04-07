# -*- coding: utf-8 -*-
#
# Copyright (c) 2013, 2015, Geoffrey T. Dairiki
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#
#   * Redistributions in binary form must reproduce the above
#     copyright notice, this list of conditions and the following
#     disclaimer in the documentation and/or other materials provided
#     with the distribution.
#
#   * Neither the name of the {organization} nor the names of its
#     contributors may be used to endorse or promote products derived
#     from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# 'AS IS' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
''' Compute a valid PEP440 version number based on git history.

If possible, the version is computed from the output of ``git describe``.
If that is successful, the version string is written to the file
``RELEASE-VERSION``.

If ``git describe`` fails (most likely because we’re in an unpacked
copy of an sdist rather than in a git working copy) then we fall back
on reading the contents of the ``RELEASE-VERSION`` file.

Usage
=====

Somewhat more detailed usage instructions, as well as the most recent
version of this code may be found at::

    https://github.com/dairiki/gitversion.

That latest version of this file is available at::

    https://raw.github.com/dairiki/gitversion/master/gitversion.py

Author
======

Author: Jeff Dairiki <dairiki@dairiki.org>

Based on work by: Douglas Creager <dcreager@dcreager.net>

'''
import errno
import os
import re
from tempfile import TemporaryFile
from subprocess import Popen, PIPE

__version__ = '1.0.2'
__all__ = ('get_version')

# Name of file in which the version number is cached
VERSION_CACHE = 'RELEASE-VERSION'


class GitError(Exception):
    pass


class GitNotFound(GitError):
    ''' The ``git`` command was not found.
    '''


class GitFailed(GitError):
    def __str__(self):
        return '{cmd!r} failed with exit status {code!r}:\n{output}'.format(
            cmd=' '.join(self.cmd),
            code=self.returncode,
            output=self.detail)

    @property
    def cmd(self):
        return self.args[0]

    @property
    def returncode(self):
        return self.args[1]

    @property
    def detail(self):
        return self.args[2]


GIT_DESCRIPION_re = re.compile(
    r'''\A \s*
        (?P<release>.*?)
        (?:
           -(?P<post>\d+)
           -g(?:[\da-f]+)               # SHA
        )?
        (?P<dirty>-dirty)?
        \s* \Z''', re.X)

# Valid PEP440 release versions
RELEASE_VERSION_re = re.compile(r'\A\d+(\.\d+)*((?:a|b|c|rc)\d+)?\Z')


def get_version(**kwargs):
    ''' Calculate a valid PEP440 version number based on git history.

    If possible the version is computed from the output of ``git describe``.
    If that is successful, the version string is written to the file
    ``RELEASE-VERSION``.

    If ``git describe`` fails (most likely because we’re in an unpacked
    copy of an sdist rather than in a git working copy) then we fall back
    on reading the contents of the ``RELEASE-VERSION`` file.

    '''
    cached_version = get_cached_version()
    git_version = get_git_version(**kwargs)

    if git_version is None:
        if cached_version is None:
            raise RuntimeError('can not determine version number')
        return cached_version

    if cached_version != git_version:
        set_cached_version(git_version)
    return git_version


def get_git_version(**kwargs):
    if not os.path.isdir('.git'):
        # Bail if we're not in the top-level git directory.
        # This avoids trouble when setup.py is being run, e.g., in a
        # tox build directory which is a subdirectory of (some other)
        # git-controlled directory.
        return None

    # This check is now redundant, but what the hell.  (If I delete
    # it, I'll forget the name of the 'rev-parse --is-inside-work-tree''
    # check.)
    try:
        run_git('rev-parse', '--is-inside-work-tree', **kwargs)
    except GitError:      # pragma: no cover
        # not a git repo, or 'git' command not found
        return None
    try:
        output = run_git('describe', '--tags', '--dirty', **kwargs)
    except GitFailed as ex:
        if ex.returncode != 128:
            raise               # pragma: no cover
        # No releases have been tagged
        return '0.dev%d' % get_number_of_commits_in_head(**kwargs)

    output = ''.join(output).strip()
    m = GIT_DESCRIPION_re.match(output)
    if not m:
        raise GitError(         # pragma: no cover
            'can not parse the output of git describe (%r)' % output)

    release, post, dirty = m.groups()
    post = int(post) if post else 0

    if not RELEASE_VERSION_re.match(release):
        raise GitError(         # pragma: no cover
            'invalid release version (%r)' % release)

    version = release
    try:
        output = run_git('rev-parse', '--short', 'HEAD', **kwargs)
        output = ''.join(output).strip()
    except GitFailed as ex:
        if ex.returncode != 128:
            raise               # pragma: no cover

    if dirty:
        version += '.post%d.dev0+%s' % (post + 1, output)
    elif post:
        version += '.post%d+%s' % (post, output)
    return version


def get_number_of_commits_in_head(**kwargs):
    try:
        return len(run_git('rev-list', 'HEAD', **kwargs))
    except GitFailed as ex:
        if ex.returncode != 128:
            raise
        return 0


def run_git(*args, **kwargs):
    git_cmd = kwargs.get('git_cmd', 'git')
    cwd = kwargs.get('cwd')
    cmd = (git_cmd,) + args
    with TemporaryFile() as stderr:
        try:
            proc = Popen(cmd, stdout=PIPE, stderr=stderr, cwd=cwd)
        except OSError as ex:
            if ex.errno == errno.ENOENT:
                raise GitNotFound('%r not found in PATH' % git_cmd)
            raise
        try:
            output = [line.decode('latin-1') for line in proc.stdout]
            if proc.wait() != 0:
                stderr.seek(0)
                errout = stderr.read().decode('latin-1')
                raise GitFailed(cmd, proc.returncode, errout.rstrip())
            return output
        finally:
            proc.stdout.close()


def get_cached_version():
    try:
        with open(VERSION_CACHE) as f:
            return f.read().strip()
    except IOError as ex:
        if ex.errno == errno.ENOENT:
            return None
        raise


def set_cached_version(version):
    with open(VERSION_CACHE, 'w') as f:
        return f.write(version + '\n')


if __name__ == '__main__':
    print(get_version())        # pragma: no cover
