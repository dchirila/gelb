/** Shared by the Extension Development Host tests (see ../runTests.js). */

const assert = require('assert');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll `cond` (may be async) until truthy or `ms` pass; its value. */
async function waitFor(cond, ms = 10000, what = 'condition') {
    const end = Date.now() + ms;
    for (;;) {
        const v = await cond();
        if (v) return v;
        if (Date.now() >= end) throw new Error(`timed out waiting for ${what}`);
        await sleep(50);
    }
}

async function activate() {
    const ext = vscode.extensions.getExtension('gelb-lang.gelb-lang');
    assert.ok(ext, 'the GeLB extension is not loaded');
    await ext.activate();
}

function status(file) {
    return vscode.commands.executeCommand('gelb.internal.runStatus', file);
}

async function waitState(state, ms = 15000) {
    return waitFor(async () => {
        const s = await status();
        return s.state === state ? s : undefined;
    }, ms, `state ${state}`);
}

/** Set the Run view's test hooks: queued answers for its questions,
 *  a start timeout, a stored per-file state. */
function hooks(o = {}) {
    return vscode.commands.executeCommand('gelb.internal.runTestHooks', o);
}

async function open(file) {
    const doc = await vscode.workspace.openTextDocument(file);
    await vscode.window.showTextDocument(doc);
    return doc;
}

function setSetting(key, value) {
    return vscode.workspace.getConfiguration('gelb')
        .update(key, value, vscode.ConfigurationTarget.Global);
}

/** The calls the fake-gelb-run in `stubDir` recorded: pid, pgid, cwd,
 *  args, and how it ended. */
function calls(stubDir) {
    const dir = path.join(stubDir, 'calls');
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir).filter(f => f.endsWith('.call')).map((f) => {
        const c = { args: [], lines: [] };
        for (const line of fs.readFileSync(path.join(dir, f), 'utf8').split('\n')) {
            if (!line) continue;
            c.lines.push(line);
            const m = /^(\w+)=(.*)$/.exec(line);
            if (!m) continue;
            if (m[1] === 'arg') c.args.push(m[2]);
            else c[m[1]] = m[2];
        }
        return c;
    }).sort((a, b) => Number(a.pid) - Number(b.pid));
}

function clearCalls(stubDir) {
    fs.rmSync(path.join(stubDir, 'calls'), { recursive: true, force: true });
}

/** The processes still in process group `pgid`. */
function groupMembers(pgid) {
    try {
        return cp.execFileSync('ps', ['-o', 'pid=,args=', '-g', String(pgid)])
            .toString().trim().split('\n').filter(Boolean);
    } catch {
        return [];          // ps exits 1 when the group is empty
    }
}

/** Stop whatever runs and wait until the view is idle (or failed). */
async function settle() {
    const s = await status();
    if (s.request) {
        await vscode.commands.executeCommand('gelb.stopRun');
        await waitFor(async () => !(await status()).request, 15000, 'no current run');
    }
}

module.exports = {
    sleep, waitFor, activate, status, waitState, hooks, open, setSetting,
    calls, clearCalls, groupMembers, settle,
};
