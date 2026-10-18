/**
 * The Run view's request lifecycle (out/runController.js) with a fake
 * executor and user interface: states, coalescing, Stop in every stage,
 * and the races between them.
 */

const assert = require('assert');

const { RunController } = require('../out/runController');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** An executor whose launches the test drives. */
function fakeExecutor() {
    const ex = {
        launches: [],
        /** Hold every launch until release() (a slow executeTask). */
        hold: false,
        failWith: undefined,
        launch(id, spec, listener) {
            const l = {
                id, spec, listener, interrupted: 0, terminated: 0,
                canInterrupt: true, pid: undefined,
            };
            l.execution = {
                interrupt: () => {
                    if (!l.canInterrupt || l.pid === undefined) return false;
                    l.interrupted++;
                    return true;
                },
                terminate: () => { l.terminated++; },
            };
            l.start = (pid = 4000 + id) => { l.pid = pid; listener.started(pid); };
            l.end = (code) => listener.ended(code);
            ex.launches.push(l);
            if (ex.failWith) return Promise.reject(new Error(ex.failWith));
            if (!ex.hold) return Promise.resolve(l.execution);
            return new Promise((resolve) => { l.release = () => resolve(l.execution); });
        },
    };
    return ex;
}

/** A user interface that records what it was told. */
function fakeUi() {
    const ui = {
        calls: [],
        states: [],
        answer: false,
        log() {},
        changed(state) { ui.states.push(state); },
        confirmStopAndRun(cur, next) {
            ui.calls.push(['confirm', cur.id, next]);
            return typeof ui.answer === 'function' ? ui.answer() : Promise.resolve(ui.answer);
        },
        coalesced(cur, next) { ui.calls.push(['coalesced', cur && cur.id, next]); },
        unconfirmed(req) { ui.calls.push(['unconfirmed', req.id]); },
        ended(req) { ui.calls.push(['ended', req.id, req.exitCode]); },
        launchFailed(req) { ui.calls.push(['launchFailed', req.id]); },
        prepareFailed(req) { ui.calls.push(['prepareFailed', req.id]); },
        stopUnconfirmed(req) { ui.calls.push(['stopUnconfirmed', req.id]); },
        nothingToStop() { ui.calls.push(['nothingToStop']); },
        named(kind) { return ui.calls.filter(c => c[0] === kind); },
    };
    return ui;
}

const TIMEOUTS = { startMs: 100, interruptGraceMs: 60, stopMs: 60 };

function setup(timeouts = TIMEOUTS) {
    const ex = fakeExecutor();
    const ui = fakeUi();
    const c = new RunController(ex, ui, { ...timeouts });
    return { ex, ui, c };
}

const ready = (spec = 'spec') => async () => spec;


describe('RunController: one run', () => {
    afterEach(() => undefined);

    it('goes idle → starting → running → idle', async () => {
        const { ex, ui, c } = setup();
        assert.strictEqual(c.state, 'idle');
        await c.run('a.gelb', ready());
        assert.strictEqual(c.state, 'starting');
        ex.launches[0].start();
        assert.strictEqual(c.state, 'running');
        ex.launches[0].end(0);
        assert.strictEqual(c.state, 'idle');
        assert.deepStrictEqual(ui.named('ended'), [['ended', 1, 0]]);
        assert.strictEqual(c.shown.exitCode, 0);
        c.dispose();
    });

    it('is failed after a non-zero exit, and the next Run starts without asking', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        ex.launches[0].start();
        ex.launches[0].end(2);
        assert.strictEqual(c.state, 'failed');
        assert.match(c.shown.failure, /exit status 2/);
        await c.run('a.gelb', ready());
        assert.strictEqual(ex.launches.length, 2);
        assert.strictEqual(ui.named('confirm').length, 0);
        c.dispose();
    });

    it('reports a launch that ends without ever having a process', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        ex.launches[0].listener.started(undefined);
        ex.launches[0].end(undefined);
        assert.strictEqual(c.state, 'failed');
        assert.match(c.shown.failure, /did not start/);
        c.dispose();
    });

    it('takes a prepare that returns nothing as "not started", not a failure', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', async () => undefined);
        assert.strictEqual(ex.launches.length, 0);
        assert.strictEqual(c.state, 'idle');
        c.dispose();
    });

    it('reports a prepare that throws, and a launch that rejects', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', async () => { throw new Error('no folder'); });
        assert.deepStrictEqual(ui.named('prepareFailed'), [['prepareFailed', 1]]);
        assert.strictEqual(c.state, 'failed');
        ex.failWith = 'no task system';
        await c.run('a.gelb', ready());
        assert.deepStrictEqual(ui.named('launchFailed'), [['launchFailed', 2]]);
        assert.strictEqual(c.state, 'failed');
        assert.strictEqual(c.busy, false);
        c.dispose();
    });

    it('handles a process that starts and ends before executeTask returns', async () => {
        const { ex, c } = setup();
        ex.hold = true;
        const p = c.run('a.gelb', ready());
        await sleep(5);
        const l = ex.launches[0];
        l.start();
        l.end(0);
        l.release();
        await p;
        assert.strictEqual(c.state, 'idle');
        assert.strictEqual(l.terminated, 0);
        c.dispose();
    });
});


describe('RunController: clicks while a run is going', () => {
    it('coalesces clicks while the first is starting: one launch', async () => {
        const { ex, ui, c } = setup();
        let release;
        const slow = () => new Promise((r) => { release = () => r('spec'); });
        const first = c.run('a.gelb', slow);
        await c.run('a.gelb', ready());
        await c.run('a.gelb', ready());
        release();
        await first;
        await c.run('a.gelb', ready());      // launched, not started yet
        assert.strictEqual(ex.launches.length, 1);
        assert.strictEqual(ui.named('coalesced').length, 3);
        c.dispose();
    });

    it('asks while running; no answer launches nothing', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        ex.launches[0].start();
        ui.answer = false;
        await c.run('b.gelb', ready());
        assert.deepStrictEqual(ui.named('confirm'), [['confirm', 1, 'b.gelb']]);
        assert.strictEqual(ex.launches.length, 1);
        assert.strictEqual(ex.launches[0].interrupted, 0);
        c.dispose();
    });

    it('Stop and Run: Ctrl-C, wait for the end, then launch', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        const first = ex.launches[0];
        first.start();
        ui.answer = true;
        const p = c.run('b.gelb', ready('b'));
        await sleep(5);
        assert.strictEqual(first.interrupted, 1);
        assert.strictEqual(ex.launches.length, 1, 'launched before the first ended');
        assert.strictEqual(c.state, 'stopping');
        first.end(130);
        await p;
        assert.strictEqual(ex.launches.length, 2);
        assert.strictEqual(ex.launches[1].spec, 'b');
        assert.strictEqual(ui.named('ended').length, 0, 'a stopped run is not reported as ended');
        c.dispose();
    });

    it('Stop and Run gives up when the first does not stop', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        const first = ex.launches[0];
        first.start();
        ui.answer = true;
        await c.run('b.gelb', ready());
        assert.strictEqual(first.interrupted, 1);
        assert.strictEqual(first.terminated, 1, 'not terminated after the grace period');
        assert.deepStrictEqual(ui.named('stopUnconfirmed'), [['stopUnconfirmed', 1]]);
        assert.strictEqual(ex.launches.length, 1);
        assert.strictEqual(c.state, 'failed');
        assert.strictEqual(c.busy, true, 'the first may still be alive');
        c.dispose();
    });

    it('a click while the question is open is coalesced', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        ex.launches[0].start();
        let answer;
        ui.answer = () => new Promise((r) => { answer = r; });
        const p = c.run('b.gelb', ready());
        await sleep(5);
        await c.run('c.gelb', ready());
        assert.deepStrictEqual(ui.named('coalesced'), [['coalesced', 1, 'c.gelb']]);
        answer(false);
        await p;
        assert.strictEqual(ex.launches.length, 1);
        c.dispose();
    });

    it('Stop while the question is open cancels the new run too', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        const first = ex.launches[0];
        first.start();
        let answer;
        ui.answer = () => new Promise((r) => { answer = r; });
        const p = c.run('b.gelb', ready());
        await sleep(5);
        await c.stop();
        first.end(130);
        answer(true);
        await p;
        assert.strictEqual(ex.launches.length, 1);
        assert.strictEqual(c.state, 'idle');
        c.dispose();
    });
});


describe('RunController: Stop in every stage', () => {
    it('with nothing going says so', async () => {
        const { ui, c } = setup();
        await c.stop();
        assert.deepStrictEqual(ui.named('nothingToStop'), [['nothingToStop']]);
    });

    it('while preparing: nothing is launched', async () => {
        const { ex, c } = setup();
        let release;
        const p = c.run('a.gelb', () => new Promise((r) => { release = () => r('spec'); }));
        await sleep(5);
        await c.stop();
        assert.strictEqual(c.state, 'idle');
        release();
        await p;
        assert.strictEqual(ex.launches.length, 0);
        assert.strictEqual(c.busy, false);
        c.dispose();
    });

    it('while the task is being created: the late execution is terminated', async () => {
        const { ex, c } = setup();
        ex.hold = true;
        const p = c.run('a.gelb', ready());
        await sleep(5);
        await c.stop();
        assert.strictEqual(c.state, 'stopping');
        const l = ex.launches[0];
        l.release();
        await p;
        assert.strictEqual(l.terminated, 1);
        l.end(undefined);
        assert.strictEqual(c.state, 'idle');
        c.dispose();
    });

    it('while starting (no process id yet): terminate', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        await c.stop();
        assert.strictEqual(ex.launches[0].terminated, 1);
        ex.launches[0].end(undefined);
        assert.strictEqual(c.state, 'idle');
        c.dispose();
    });

    it('while running: Ctrl-C first, terminate only if it is still going', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        const l = ex.launches[0];
        l.start();
        const stopped = c.stop();
        assert.strictEqual(l.interrupted, 1);
        assert.strictEqual(l.terminated, 0);
        l.end(130);
        await stopped;
        await sleep(TIMEOUTS.interruptGraceMs + 20);
        assert.strictEqual(l.terminated, 0, 'terminated although it had ended');
        assert.strictEqual(c.state, 'idle');
        assert.ok(c.shown.stopRequested);
        c.dispose();
    });

    it('a second Stop terminates at once', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        const l = ex.launches[0];
        l.start();
        void c.stop();
        await c.stop();
        assert.strictEqual(l.interrupted, 1);
        assert.strictEqual(l.terminated, 1);
        c.dispose();
    });

    it('after the start was not confirmed: terminate, and the run is over', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        await sleep(TIMEOUTS.startMs + 20);
        assert.deepStrictEqual(ui.named('unconfirmed'), [['unconfirmed', 1]]);
        assert.strictEqual(c.state, 'failed');
        assert.strictEqual(c.busy, true);
        await c.stop();
        assert.strictEqual(ex.launches[0].terminated, 1);
        ex.launches[0].end(undefined);
        assert.strictEqual(c.state, 'idle');
        c.dispose();
    });
});


describe('RunController: late and stale events', () => {
    it('a start after the timeout makes the run running again', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        await sleep(TIMEOUTS.startMs + 20);
        assert.strictEqual(c.state, 'failed');
        ex.launches[0].start();
        assert.strictEqual(c.state, 'running');
        assert.strictEqual(c.shown.failure, undefined);
        c.dispose();
    });

    it('no automatic retry after an unconfirmed start', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        await sleep(TIMEOUTS.startMs * 3);
        assert.strictEqual(ex.launches.length, 1);
        c.dispose();
    });

    it('events of an earlier request do not touch the current one', async () => {
        const { ex, ui, c } = setup();
        await c.run('a.gelb', ready());
        const old = ex.launches[0];
        old.start();
        ui.answer = true;
        const p = c.run('b.gelb', ready());
        await sleep(5);
        old.end(130);
        await p;
        const cur = ex.launches[1];
        cur.start();
        assert.strictEqual(c.state, 'running');
        old.end(0);                           // a duplicate, late end
        old.listener.started(1234);           // and a late start
        assert.strictEqual(c.state, 'running');
        assert.strictEqual(c.request.id, 2);
        c.dispose();
    });

    it('a timeout armed for an earlier request does not fire on the current one', async () => {
        const { ex, c } = setup();
        await c.run('a.gelb', ready());
        ex.launches[0].start();
        ex.launches[0].end(0);
        await c.run('a.gelb', ready());
        ex.launches[1].start();
        await sleep(TIMEOUTS.startMs + 20);
        assert.strictEqual(c.state, 'running');
        c.dispose();
    });
});


describe('RunController: adopting a run from before a reload', () => {
    it('a run that ended with the last window is shown as failed', () => {
        const { c } = setup();
        c.noteLost(7, 'a.gelb', 'ended with the window (reloaded or closed)');
        assert.strictEqual(c.state, 'failed');
        assert.strictEqual(c.shown.id, 7);
        assert.strictEqual(c.busy, false);
    });

    it('follows it as running; Stop terminates it (no process id)', async () => {
        const { c } = setup();
        let listener;
        let terminated = 0;
        c.adopt('a.gelb', (l) => {
            listener = l;
            return { interrupt: () => false, terminate: () => { terminated++; } };
        });
        assert.strictEqual(c.state, 'running');
        await c.stop();
        assert.strictEqual(terminated, 1);
        listener.ended(undefined);
        assert.strictEqual(c.state, 'idle');
        c.dispose();
    });
});
