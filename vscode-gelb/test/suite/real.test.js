/**
 * The Run view with the real scripts/gelb-run of this checkout, found
 * the way users' files find it (the file is inside the checkout): a
 * short run, then a run whose viewer is stopped. Only with
 * GELB_TEST_REAL=1 (it compiles; minutes on a cold cache).
 */

const assert = require('assert');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const h = require('./helpers');

const CHECKOUT = process.env.GELB_TEST_CHECKOUT;
const FILE = path.join(CHECKOUT, 'examples', 'lbm', '2d', 'lid_driven_cavity_2d_bgk.gelb');
const OUT = path.join(process.env.GELB_TEST_ROOT, 'real runs');
const NC = path.join(OUT, 'lid_driven_cavity_2d_bgk.nc');

const run = (arg) => vscode.commands.executeCommand('gelb.run', arg);
const params = (patch) => h.hooks({ setState: { file: FILE, patch } });

/** Viewer processes (python, uv or gelb-view itself) on `nc`. */
function viewersOf(nc) {
    return cp.execFileSync('ps', ['-eo', 'pid=,pgid=,args=']).toString()
        .split('\n').filter(l => /^\s*\d+\s+\d+\s+\S*(python[\d.]*|uv|gelb-view)\s/.test(l)
            && /gelb[-_]view/.test(l) && l.includes(nc));
}


describe('Run view with the real gelb-run', function () {
    this.timeout(600000);
    let doc;

    before(async () => {
        doc = await h.open(FILE);
        await h.activate();
        await h.setSetting('gelbRunCommand', '');
    });

    after(async () => {
        await h.settle();
    });

    it('finds scripts/gelb-run of the checkout and runs the example', async () => {
        await params({ outputFolder: OUT, timeSteps: 20, writeEvery: 10, view: false });
        await run(doc.uri);
        const s = await h.waitState('idle', 600000);
        assert.strictEqual(s.shown.exitCode, 0, s.log.join('\n'));
        assert.strictEqual(s.shown.spec.runner, path.join(CHECKOUT, 'scripts', 'gelb-run'));
        assert.ok(fs.existsSync(NC));
        assert.strictEqual((await h.status(FILE)).stored.lastOutput, NC);
    });

    it('Stop while gelb-view is open ends gelb-run and the viewer', async () => {
        await params({ outputFolder: OUT, timeSteps: 20, writeEvery: 10, view: true });
        await h.hooks({});
        await run(doc.uri);
        // The task's process leads its own process group.
        const pgid = await h.waitFor(async () => (await h.status()).request?.pid,
            60000, 'the run to start');
        const viewer = await h.waitFor(
            () => h.groupMembers(pgid).find(l => /gelb[-_]view/.test(l)), 600000, 'gelb-view');
        assert.ok(viewersOf('lid_driven_cavity_2d_bgk.nc').length >= 1, viewer);
        assert.strictEqual((await h.status()).state, 'running');
        await vscode.commands.executeCommand('gelb.stopRun');
        await h.waitState('idle', 20000);
        await h.waitFor(() => h.groupMembers(pgid).length === 0, 10000, 'the group to empty');
        assert.deepStrictEqual(viewersOf('lid_driven_cavity_2d_bgk.nc'), []);
    });
});
