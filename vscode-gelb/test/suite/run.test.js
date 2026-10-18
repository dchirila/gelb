/**
 * The Run view in a real VS Code window with a folder open, against
 * fake-gelb-run (see fixture/). Each test names the scenario it covers
 * and the behaviour it expects.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const h = require('./helpers');

const ROOT = process.env.GELB_TEST_ROOT;
const WS = process.env.GELB_TEST_WS;
const STUB = process.env.GELB_TEST_STUB;
const STUB_DIR = path.dirname(STUB);
const SHELL_DIR = process.env.GELB_TEST_SHELL_STUB_DIR;
const FILE = path.join(WS, 'my sims', 'cavity.gelb');
const OTHER = path.join(WS, 'other.gelb');
const OUT = path.join(WS, 'runs with space');
const NC = path.join(OUT, 'cavity.nc');

const run = (arg) => vscode.commands.executeCommand('gelb.run', arg);
const stop = () => vscode.commands.executeCommand('gelb.stopRun');

/** Store this file's Run parameters, e.g. { defines: [['SLEEP', '30']] }. */
const params = (patch) => h.hooks({ setState: { file: FILE, patch } });


describe('Run view in an Extension Development Host', function () {
    this.timeout(60000);
    let doc;

    before(async () => {
        await h.activate();
        doc = await h.open(FILE);
    });

    beforeEach(async () => {
        await h.settle();
        await h.setSetting('gelbRunCommand', STUB);
        await params({ outputFolder: OUT, view: false, defines: undefined });
        h.clearCalls(STUB_DIR);
        h.clearCalls(SHELL_DIR);
    });

    after(async () => {
        await h.settle();
    });

    it('fresh launch: one execution, arguments intact (spaces, -D values), output in the chosen folder', async () => {
        await params({ defines: [['TAU', '1.0 / 1.6'], ['SLEEP', '1']] });
        await run(doc.uri);
        await h.waitState('running');
        const s = await h.waitState('idle');
        assert.strictEqual(s.shown.exitCode, 0);
        const c = h.calls(STUB_DIR);
        assert.strictEqual(c.length, 1);
        assert.strictEqual(c[0].cwd, OUT);
        assert.deepStrictEqual(c[0].args,
            ['-n', '1000', '-w', '100', '-D', 'TAU=1.0 / 1.6', '-D', 'SLEEP=1', FILE]);
        assert.ok(fs.existsSync(NC));
        assert.strictEqual((await h.status(FILE)).stored.lastOutput, NC);
        assert.ok(s.log.some(l => /command: cd '.*runs with space' && '.*fake-gelb-run' -n 1000/.test(l)),
            s.log.join('\n'));
    });

    it('partial command, input reader, same-named terminals: nothing is typed into them', async () => {
        const typed = path.join(ROOT, 'typed.txt');
        fs.rmSync(typed, { force: true });
        const reader = vscode.window.createTerminal({
            name: 'GeLB run', shellPath: '/bin/sh', shellArgs: ['-c', `cat > '${typed}'`],
        });
        const partial = vscode.window.createTerminal({ name: 'GeLB run' });
        await h.waitFor(() => fs.existsSync(typed), 10000, 'the reader to start');
        await h.sleep(1000);
        partial.sendText('echo ', false);
        await run(doc.uri);
        await h.waitState('idle');
        assert.strictEqual(h.calls(STUB_DIR).length, 1);
        reader.sendText('\u0004', false);
        await h.waitFor(() => reader.exitStatus !== undefined, 10000, 'the reader to end');
        assert.strictEqual(fs.readFileSync(typed, 'utf8'), '');
        reader.dispose();
        partial.dispose();
    });

    it('rapid triple click while starting: one execution, the others coalesced', async () => {
        await params({ defines: [['SLEEP', '1']] });
        await h.hooks({});
        await Promise.all([run(doc.uri), run(doc.uri), run(doc.uri)]);
        const s = await h.waitState('idle');
        assert.strictEqual(h.calls(STUB_DIR).length, 1);
        assert.strictEqual(s.messages.filter(m => m.startsWith('coalesced')).length, 2);
    });

    it('Stop during the simulation: Ctrl-C reaches gelb-run and its children', async () => {
        await params({ defines: [['SLEEP', '60']] });
        await run(doc.uri);
        await h.waitState('running');
        const c = await h.waitFor(() => h.calls(STUB_DIR).find(x => x.child), 10000, 'the child');
        assert.ok(h.groupMembers(c.pgid).length >= 2, h.groupMembers(c.pgid).join('\n'));
        await stop();
        const s = await h.waitState('idle', 10000);
        assert.ok(s.shown.stopRequested);
        await h.waitFor(() => h.groupMembers(c.pgid).length === 0, 5000, 'the group to empty');
        assert.ok(h.calls(STUB_DIR)[0].lines.includes('interrupted'));
    });

    it('Stop while the viewer is open (gelb-run --view waits for it)', async () => {
        await params({ view: true });
        await run(doc.uri);
        const c = await h.waitFor(() => h.calls(STUB_DIR).find(x => x.viewer), 10000, 'the viewer');
        assert.strictEqual((await h.status()).state, 'running');
        await stop();
        await h.waitState('idle', 10000);
        await h.waitFor(() => h.groupMembers(c.pgid).length === 0, 5000, 'the group to empty');
    });

    it('Stop when Ctrl-C is ignored: the task is terminated after the grace period', async () => {
        await params({ defines: [['SLEEP', '60'], ['IGNOREINT', '1']] });
        await run(doc.uri);
        await h.waitState('running');
        const c = await h.waitFor(() => h.calls(STUB_DIR).find(x => x.child), 10000, 'the child');
        const t0 = Date.now();
        const stopped = stop();              // resolves when the run has ended
        await h.sleep(1000);
        assert.strictEqual((await h.status()).state, 'stopping');
        assert.ok(h.groupMembers(c.pgid).length >= 2, 'Ctrl-C was not ignored');
        await stopped;
        assert.ok(Date.now() - t0 >= 2500, 'terminated before the grace period');
        await h.waitState('idle', 15000);
        await h.waitFor(() => h.groupMembers(c.pgid).length === 0, 5000, 'the group to empty');
        assert.ok(h.calls(STUB_DIR)[0].lines.includes('hangup'));
    });

    it('Stop racing with the launch: nothing is left running', async () => {
        await params({ defines: [['SLEEP', '60']] });
        const p = run(doc.uri);
        await stop();
        await p;
        await h.waitFor(async () => !(await h.status()).request, 15000, 'no current run');
        await h.sleep(2000);
        for (const c of h.calls(STUB_DIR)) {
            assert.deepStrictEqual(h.groupMembers(c.pgid), []);
        }
        assert.notStrictEqual((await h.status()).state, 'failed');
    });

    it('unrelated task start and end: the run is unaffected', async () => {
        await params({ defines: [['SLEEP', '30']] });
        await run(doc.uri);
        await h.waitState('running');
        const task = new vscode.Task({ type: 'shell' }, vscode.TaskScope.Workspace,
            'unrelated', 'test', new vscode.ShellExecution('true'));
        const ended = new Promise((resolve) => {
            const d = vscode.tasks.onDidEndTaskProcess((e) => {
                if (e.execution.task.name === 'unrelated') { d.dispose(); resolve(); }
            });
        });
        await vscode.tasks.executeTask(task);
        await ended;
        await h.sleep(300);
        assert.strictEqual((await h.status()).state, 'running');
    });

    it('nonzero exit with an older output present: reported, the last output unchanged', async () => {
        await params({ defines: [['SLEEP', '0']] });
        await run(doc.uri);
        await h.waitState('idle');
        const before = fs.statSync(NC).mtimeMs;
        await params({ defines: [['EXIT', '3'], ['NOOUT', '1']] });
        await h.hooks({});
        await run(doc.uri);
        const s = await h.waitState('failed');
        assert.match(s.shown.failure, /exit status 3/);
        assert.ok(s.messages.some(m => /exited with status 3/.test(m)), s.messages.join('\n'));
        assert.ok(s.log.some(l => /cavity\.nc is from an earlier run/.test(l)), s.log.join('\n'));
        assert.strictEqual(fs.statSync(NC).mtimeMs, before);
    });

    it('missing executable: an actionable message, nothing launched', async () => {
        await h.setSetting('gelbRunCommand', path.join(ROOT, 'no such dir', 'gelb-run'));
        await h.hooks({});
        await run(doc.uri);
        const s = await h.status();
        assert.strictEqual(s.request, undefined);
        assert.ok(s.messages.some(m => /not an executable file/.test(m)), s.messages.join('\n'));
        assert.strictEqual(h.calls(STUB_DIR).length, 0);
    });

    it('invalid output folder: an actionable message, nothing launched', async () => {
        await params({ outputFolder: path.join(FILE, 'below a file') });
        await h.hooks({});
        await run(doc.uri);
        const s = await h.status();
        assert.strictEqual(s.state, 'failed');
        assert.ok(s.messages.some(m => /cannot create the output folder/.test(m)), s.messages.join('\n'));
        assert.strictEqual(h.calls(STUB_DIR).length, 0);
    });

    it('runner setting changes between requests: the first stays identifiable and stoppable', async () => {
        const otherDir = path.join(ROOT, 'other bin');
        fs.mkdirSync(otherDir, { recursive: true });
        const other = path.join(otherDir, 'fake-gelb-run');
        fs.copyFileSync(STUB, other);
        fs.chmodSync(other, 0o755);
        h.clearCalls(otherDir);
        await params({ defines: [['SLEEP', '60']] });
        await run(doc.uri);
        await h.waitState('running');
        const first = (await h.status()).request.id;
        const c = await h.waitFor(() => h.calls(STUB_DIR).find(x => x.child), 10000, 'the child');
        await h.setSetting('gelbRunCommand', other);

        await h.hooks({ answers: [undefined] });
        await run(doc.uri);
        let s = await h.status();
        assert.ok(s.messages.some(m => /still going/.test(m)));
        assert.strictEqual(s.request.id, first);
        assert.strictEqual(h.calls(otherDir).length, 0);

        await params({ defines: [['SLEEP', '0']] });
        await h.hooks({ answers: ['Stop and Run'] });
        await run(doc.uri);
        await h.waitFor(() => h.groupMembers(c.pgid).length === 0, 10000, 'the first to stop');
        s = await h.waitState('idle');
        assert.notStrictEqual(s.shown.id, first);
        assert.strictEqual(h.calls(otherDir).length, 1);
    });

    it('bare gelb-run found only through the task shell, whose startup changes directory', async () => {
        const read = path.join(ROOT, 'bash_env.read');
        fs.rmSync(read, { force: true });
        await h.setSetting('gelbRunCommand', 'fake-gelb-run');
        await params({ defines: [['SLEEP', '0']] });
        await run(doc.uri);
        const s = await h.waitState('idle');
        assert.strictEqual(s.shown.exitCode, 0);
        assert.strictEqual(h.calls(STUB_DIR).length, 0);
        const c = h.calls(SHELL_DIR);
        assert.strictEqual(c.length, 1);
        assert.strictEqual(c[0].cwd, OUT);
        assert.strictEqual(c[0].args[c[0].args.length - 1], FILE);
        // The shell did read its startup file, which moved it to /.
        assert.ok(fs.existsSync(read), 'the task shell did not read BASH_ENV');
    });

    it('bare gelb-run that no shell finds: exit status 127, reported as a setup problem', async () => {
        await h.setSetting('gelbRunCommand', 'no-such-gelb-run');
        await h.hooks({});
        await run(doc.uri);
        const s = await h.waitState('failed');
        assert.strictEqual(s.shown.exitCode, 127);
        assert.ok(s.messages.some(m => /task shell could not find "no-such-gelb-run"/.test(m)),
            s.messages.join('\n'));
    });

    it('dirty source and an editor switch during the launch: the saved first file runs', async () => {
        await params({ defines: [['SLEEP', '0']] });
        const editor = await vscode.window.showTextDocument(doc);
        await editor.edit(e => e.insert(new vscode.Position(0, 0), '// edited\n'));
        assert.ok(doc.isDirty);
        const p = run();                     // the shown document
        await h.open(OTHER);
        await p;
        await h.waitState('idle');
        const c = h.calls(STUB_DIR);
        assert.strictEqual(c.length, 1);
        assert.strictEqual(c[0].args[c[0].args.length - 1], FILE);
        assert.ok(fs.readFileSync(FILE, 'utf8').startsWith('// edited\n'));
        await h.open(FILE);
    });

    it('Stop with nothing going says so', async () => {
        await h.hooks({});
        await stop();
        assert.ok((await h.status()).messages.includes('GeLB: no run is going.'));
    });
});
