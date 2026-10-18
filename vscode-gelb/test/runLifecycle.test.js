/**
 * Regressions for the Run view's lifecycle defects fixed in 0.6.0:
 * RunProvider from out/ driven through a fake `vscode` module
 * (fakeVscode.js), which records every launch, whether a line typed
 * into a terminal or a task executed, and lets the test decide when a
 * launched process starts and ends.
 *
 * The same scenarios run against any implementation of the Run view;
 * on 0.5.0 (a line typed into the "GeLB run" terminal) they fail.
 */

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const fake = require('./fakeVscode');
fake.install();
const { RunProvider } = require('../out/runView');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll `cond` until it holds or `ms` pass; returns its last value. */
async function waitFor(cond, ms) {
    const end = Date.now() + ms;
    for (;;) {
        const v = cond();
        if (v || Date.now() >= end) return v;
        await sleep(20);
    }
}

let tmp;
let world;
let provider;
let doc;
let subs;

function makeRunner(name) {
    const p = path.join(tmp, 'bin', name);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, '#!/bin/sh\nexit 0\n', { mode: 0o755 });
    return p;
}

function launches() {
    return world.launches.length;
}

function warnings(re) {
    return world.messages.filter(m => m.level === 'warning' && re.test(m.message));
}

beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gelb-run-lifecycle-'));
    world = fake.reset();
    const ws = path.join(tmp, 'ws');
    fs.mkdirSync(ws);
    world.workspaceFolders = [{ uri: fake.Uri.file(ws), name: 'ws', index: 0 }];
    const file = path.join(ws, 'cavity.gelb');
    fs.writeFileSync(file, 'simulation_description("cavity")\n');
    doc = fake.addDocument(file, 'simulation_description("cavity")\n');
    world.config['gelb.gelbRunCommand'] = makeRunner('gelb-run');
    provider = new RunProvider(fake.fakeContext());
    subs = provider.register();
});

afterEach(async () => {
    // Let a run still holding its queue (0.5.0: up to 3 s) drain, so it
    // cannot leak into the next test.
    await provider.stop?.();
    if (provider.runQueue) await Promise.race([provider.runQueue, sleep(4000)]);
    for (const s of subs) s.dispose?.();
    fs.rmSync(tmp, { recursive: true, force: true });
});


describe('Run lifecycle regressions', function () {
    this.timeout(15000);

    it('a second Run while the first is still going asks instead of launching', async () => {
        world.answer = () => undefined;          // the question is dismissed
        await provider.run(doc.uri);
        assert.strictEqual(launches(), 1);
        await waitFor(() => world.launches[0].started, 1000);
        // The first run is going (no end event); nothing tells the
        // extension otherwise.
        await provider.run(doc.uri);
        assert.strictEqual(launches(), 1, 'a second run was launched behind the first');
        assert.strictEqual(warnings(/still going/i).length, 1, 'no question was asked');
    });

    it('the previous run stays identifiable after the runner setting changes', async () => {
        world.answer = () => undefined;
        await provider.run(doc.uri);
        await waitFor(() => world.launches[0].started, 1000);
        world.config['gelb.gelbRunCommand'] = makeRunner('gelb-run-other');
        await provider.run(doc.uri);
        assert.strictEqual(launches(), 1, 'a run with the new runner was launched behind the old one');
        assert.strictEqual(warnings(/still going/i).length, 1);
    });

    it('a launch that never reports its start is reported to the user', async () => {
        world.autoStart = false;
        provider.startTimeoutMs = 200;
        await provider.run(doc.uri);
        assert.strictEqual(launches(), 1);
        const w = await waitFor(() => warnings(/not (yet )?(been )?(reported|confirmed|started)|has not started/i)[0], 4500);
        assert.ok(w, 'the unconfirmed start was not reported');
        assert.ok(w.items.some(i => /show/i.test(typeof i === 'string' ? i : i.title)),
            'the report offers no way to see the output');
        assert.strictEqual(world.contexts['gelb.runInProgress'], true,
            'Stop must stay available while the launch may still start');
    });

    it('Stop cancels a Run requested while the first was starting', async () => {
        world.autoStart = false;
        provider.startTimeoutMs = 10000;
        const first = provider.run(doc.uri);
        await sleep(50);
        const second = provider.run(doc.uri);
        await sleep(50);
        await provider.stop();
        await Promise.race([Promise.all([first, second]), sleep(4500)]);
        await sleep(200);
        assert.ok(launches() <= 1, `${launches()} launches after Stop`);
        assert.ok(world.launches.every(l => l.stopped || l.ended),
            'the launched run was not stopped');
        assert.strictEqual(world.contexts['gelb.runInProgress'], false);
    });

    it('an unrelated end event does not end the run', async () => {
        await provider.run(doc.uri);
        await waitFor(() => world.launches[0].started, 1000);
        assert.strictEqual(world.contexts['gelb.runInProgress'], true);
        world.fireUnrelatedEnd();
        await sleep(50);
        assert.strictEqual(world.contexts['gelb.runInProgress'], true,
            'an end event of another command cleared the running state');
    });

    it('an unrelated start event does not count as the start of the run', async () => {
        world.autoStart = false;
        provider.startTimeoutMs = 10000;
        world.answer = () => undefined;
        const first = provider.run(doc.uri);
        await sleep(50);
        world.fireUnrelatedStart();
        const second = provider.run(doc.uri);
        await Promise.race([Promise.all([first, second]), sleep(4500)]);
        assert.strictEqual(launches(), 1, 'a second run was launched behind the first');
    });
});
