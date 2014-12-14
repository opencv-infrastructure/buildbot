from twisted.internet import defer
import datetime

def printData(d):
    print str(datetime.datetime.now()) + ': ' + d

class DeferredSharedLock(defer.DeferredSemaphore):
    def __init__(self, tokens):
        defer.DeferredSemaphore.__init__(self, tokens)
        self.exclusiveLock = defer.DeferredLock()

    def _releaseAndReturnExclusive(self, r):
        self.releaseExclusive()
        return r

    def runExclusive(self, f, *args, **kwargs):
        def executeExclusive(ignoredResult):
            d = defer.maybeDeferred(f, *args, **kwargs)
            d.addBoth(self._releaseAndReturnExclusive)
            return d

        d = self.acquireExclusive()
        d.addCallback(executeExclusive)
        return d


    def _cancelAcquireExclusive(self, d):
        printData('_cancelAcquireExclusive')
        d = d.d_exclusiveLock
        if d.called:
            assert not d.result.called
            for dm in d.result.dl:
                if not dm.called:
                    self.waiting.remove(dm)
            for dm in d.result.dl:
                if dm.called:
                    defer.DeferredSemaphore.release(self)
            self.exclusiveLock.release()
        else:
            self.exclusiveLock.waiting.remove(d)

    def acquire(self):
        printData('acquire')
        d = defer.DeferredSemaphore.acquire(self)
        def doneAcquire(_):
            printData('acquired')
        d.addBoth(doneAcquire)
        return d


    def release(self):
        printData('release')
        return defer.DeferredSemaphore.release(self)


    def acquireExclusive(self):
        printData('acquireExclusive')
        complete = defer.Deferred()
        def _do(*args):
            printData('acquireExclusiveInner')
            dl = []
            for i in range(self.limit):
                d = defer.DeferredSemaphore.acquire(self)
                def doneAcquire(lock, _):
                    printData('acquiredExclusive step: ' + str(_))
                d.addBoth(doneAcquire, i)
                dl.append(d)
            def doneAcquire(*args):
                printData('acquiredExclusive')
                complete.callback(*args)
            d = defer.gatherResults(dl)
            d.dl = dl
            d.addBoth(doneAcquire)
            return d
        d = self.exclusiveLock.run(_do)
        complete.d_exclusiveLock = d
        return complete


    def releaseExclusive(self):
        printData('releaseExclusive')
        for i in range(self.limit):
            printData('releaseExclusive step: ' + str(i))
            defer.DeferredSemaphore.release(self)
