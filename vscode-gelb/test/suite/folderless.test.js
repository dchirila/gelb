/**
 * The Run view in a window without a folder (a single .gelb file
 * opened): VS Code starts a new task terminal there only in the home
 * folder, and refuses the first launch elsewhere without a process.
 */

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const h = require('./helpers');

const WS = process.env.GELB_TEST_WS;
const STUB = process.env.GELB_TEST_STUB;
const STUB_DIR = path.dirname(STUB);
const SHELL_DIR = process.env.GELB_TEST_SHELL_STUB_DIR;
const FILE = path.join(WS, 'my sims', 'cavity.gelb');

const run = (arg) => vscode.commands.executeCommand('gelb.run', arg);
const params = (patch) => h.hooks({ setState: { file: FILE, patch } });


describe('Run view in a window without a folder', function () {
    this.timeout(60000);
    let doc;

    before(async () => {
        assert.strictEqual(vscode.workspace.workspaceFolders, undefined);
        doc = await h.open(FILE);
        await h.activate();
    });

    beforeEach(async () => {
        await h.settle();
        await h.setSetting('gelbRunCommand', STUB);
        h.clearCalls(STUB_DIR);
        h.clearCalls(SHELL_DIR);
    });

    it('the first Run starts, next to the source file', async () => {
        await params({ defines: [['SLEEP', '0']], view: false });
        await run(doc.uri);
        const s = await h.waitState('idle');
        assert.strictEqual(s.shown.exitCode, 0, JSON.stringify(s.shown));
        const c = h.calls(STUB_DIR);
        assert.strictEqual(c.length, 1);
        assert.strictEqual(c[0].cwd, path.dirname(FILE));
        assert.strictEqual(c[0].args[c[0].args.length - 1], FILE);
    });

    it('a chosen output folder (with spaces) and a stop', async () => {
        const out = path.join(WS, 'folderless runs');
        await params({ defines: [['SLEEP', '60']], outputFolder: out });
        await run(doc.uri);
        await h.waitState('running');
        const c = await h.waitFor(() => h.calls(STUB_DIR).find(x => x.child), 10000, 'the child');
        assert.strictEqual(c.cwd, out);
        await vscode.commands.executeCommand('gelb.stopRun');
        await h.waitState('idle', 10000);
        await h.waitFor(() => h.groupMembers(c.pgid).length === 0, 5000, 'the group to empty');
    });

    it('a bare gelb-run through the task shell', async () => {
        await h.setSetting('gelbRunCommand', 'fake-gelb-run');
        await params({ defines: [['SLEEP', '0']], outputFolder: undefined });
        await run(doc.uri);
        const s = await h.waitState('idle');
        assert.strictEqual(s.shown.exitCode, 0);
        const c = h.calls(SHELL_DIR);
        assert.strictEqual(c.length, 1);
        assert.strictEqual(c[0].cwd, path.dirname(FILE));
    });
});
