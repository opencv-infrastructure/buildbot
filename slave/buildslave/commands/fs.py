# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

import glob
import os
import shutil
import sys
import traceback

from twisted.internet import defer
from twisted.internet import reactor
from twisted.internet import task
from twisted.internet import threads
from twisted.python import log
from twisted.python import runtime

from buildslave import runprocess
from buildslave.commands import base
from buildslave.commands import utils

class MakeDirectory(base.Command):

    header = "mkdir"

    # args['dir'] is relative to Builder directory, and is required.
    requiredArgs = ['dir']

    @defer.inlineCallbacks
    def start(self):
        dirname = os.path.join(self.builder.basedir, self.args['dir'])

        rc = 1
        for i in range(1, 10):
            try:
                if not os.path.isdir(dirname):
                    os.makedirs(dirname)
                rc = 0
                break
            except OSError, e:
                rc = e.errno
                log.msg("MakeDirectory %s failed" % dirname, e)
                if not os.path.isdir(dirname):
                    # delay after error
                    yield task.deferLater(reactor, 30, lambda: None)
                    if os.path.exists(dirname):
                        if not os.path.isdir(dirname):
                            log.msg('... mkdir path %s exists (but not directory)' % dirname)
                            break
                else:
                    log.msg('... but directory exists: %s' % dirname)
                
        log.msg('... MakeDirectory %s: rc=%d' % (dirname, rc))
        self.sendStatus({'rc': rc})


class RemoveDirectory(base.Command):

    header = "rmdir"

    # args['dir'] is relative to Builder directory, and is required.
    requiredArgs = ['dir']

    def setup(self, args):
        self.logEnviron = args.get('logEnviron', True)

    @defer.deferredGenerator
    def start(self):
        args = self.args
        dirnames = args['dir']

        self.timeout = args.get('timeout', 600)
        self.maxTime = args.get('maxTime', None)
        self.rc = 0
        if isinstance(dirnames, list):
            assert len(dirnames) != 0
            for dirname in dirnames:
                wfd = defer.waitForDeferred(self.removeSingleDir(dirname))
                yield wfd
                res = wfd.getResult()
                # Even if single removal of single file/dir consider it as
                # failure of whole command, but continue removing other files
                # Send 'rc' to master to handle failure cases
                if res != 0:
                    self.rc = res
        else:
            wfd = defer.waitForDeferred(self.removeSingleDir(dirnames))
            yield wfd
            self.rc = wfd.getResult()

        self.sendStatus({'rc': self.rc})


class CopyDirectory(base.Command):

    header = "cpdir"

    # args['todir'] and args['fromdir'] are relative to Builder directory, and are required.
    requiredArgs = ['todir', 'fromdir']

    def setup(self, args):
        self.logEnviron = args.get('logEnviron', True)

    def start(self):
        args = self.args

        fromdir = os.path.join(self.builder.basedir, self.args['fromdir'])
        todir = os.path.join(self.builder.basedir, self.args['todir'])

        self.timeout = args.get('timeout', 120)
        self.maxTime = args.get('maxTime', None)

        if runtime.platformType != "posix":
            d = threads.deferToThread(shutil.copytree, fromdir, todir)

            def cb(_):
                return 0  # rc=0

            def eb(f):
                self.sendStatus({'header': 'exception from copytree\n' + f.getTraceback()})
                return -1  # rc=-1
            d.addCallbacks(cb, eb)

            @d.addCallback
            def send_rc(rc):
                self.sendStatus({'rc': rc})
        else:
            if not os.path.exists(os.path.dirname(todir)):
                os.makedirs(os.path.dirname(todir))
            if os.path.exists(todir):
                # I don't think this happens, but just in case..
                log.msg("cp target '%s' already exists -- cp will not do what you think!" % todir)

            command = ['cp', '-R', '-P', '-p', '-v', fromdir, todir]
            c = runprocess.RunProcess(self.builder, command, self.builder.basedir,
                                      sendRC=False, timeout=self.timeout, maxTime=self.maxTime,
                                      logEnviron=self.logEnviron, usePTY=False)
            self.command = c
            d = c.start()
            d.addCallback(self._abandonOnFailure)

            d.addCallbacks(self._sendRC, self._checkAbandoned)
        return d


class StatFile(base.Command):

    header = "stat"

    # args['file'] is relative to Builder directory, and is required.
    requireArgs = ['file']

    def start(self):
        filename = os.path.join(self.builder.basedir, self.args['file'])

        try:
            stat = os.stat(filename)
            self.sendStatus({'stat': tuple(stat)})
            self.sendStatus({'rc': 0})
        except OSError, e:
            log.msg("StatFile %s failed" % filename, e)
            self.sendStatus({'header': '%s: %s: %s' % (self.header, e.strerror, filename)})
            self.sendStatus({'rc': e.errno})


class GlobPath(base.Command):

    header = "glob"

    # args['path'] is relative to Builder directory, and is required.
    requiredArgs = ['path']

    def start(self):
        pathname = os.path.join(self.builder.basedir, self.args['path'])

        try:
            files = glob.glob(pathname)
            self.sendStatus({'files': files})
            self.sendStatus({'rc': 0})
        except OSError, e:
            log.msg("GlobPath %s failed" % pathname, e)
            self.sendStatus({'header': '%s: %s: %s' % (self.header, e.strerror, pathname)})
            self.sendStatus({'rc': e.errno})


class ListDir(base.Command):

    header = "listdir"

    # args['dir'] is relative to Builder directory, and is required.
    requireArgs = ['dir']

    def start(self):
        dirname = os.path.join(self.builder.basedir, self.args['dir'])

        try:
            files = os.listdir(dirname)
            self.sendStatus({'files': files})
            self.sendStatus({'rc': 0})
        except OSError, e:
            log.msg("ListDir %s failed" % dirname, e)
            self.sendStatus({'header': '%s: %s: %s' % (self.header, e.strerror, dirname)})
            self.sendStatus({'rc': e.errno})
