#!/usr/bin/env node
/**
 * gen_vscode_screenshots.mjs -- the VS Code screenshots of the GeLB User
 * Tutorial (docs/user/figures/vscode_*.png), taken in a clean VS Code.
 *
 * Usage, from the repository root (Linux, with VS Code and xvfb):
 *
 *     node scripts/gen_vscode_screenshots.mjs [--keep]
 *
 * What it does:
 *   1. installs the extension with ./scripts/install-vscode-ext.sh into a
 *      throwaway extensions folder (nothing else is installed there);
 *   2. re-runs itself under `xvfb-run` (WAYLAND_DISPLAY unset, X11), so
 *      nothing appears on the desktop; without xvfb-run it stops and says
 *      how to install it, rather than using the real display;
 *   3. starts VS Code (/usr/share/code/code, or GELB_VSCODE) through
 *      Playwright's Electron driver with a throwaway --user-data-dir, the
 *      light theme, no minimap, no status bar, AI features and the Chat
 *      view off, 2x device scale, on a temporary folder holding a copy of
 *      the lid-driven cavity example;
 *   4. drives it to each state, waits for it, outlines what the text
 *      points at, and saves the region (editor, panel or view) as a PNG:
 *        vscode_editor.png    the example open: highlighting, the Run
 *                             CodeLens and the editor's title buttons
 *        vscode_problems.png  a misspelt name after saving: the
 *                             squiggle and the Problems panel entry
 *        vscode_preview.png   GeLB: Show Source Preview (geometry)
 *        vscode_run.png       the Run view while a run is going
 *        vscode_gelb_view.png the viewer the run opened
 *   5. removes the temporary folders (--keep leaves them, for a look).
 *
 * The virtual screen is 3200x2000: at the 2x scale that keeps the images
 * sharp in print, VS Code then has 1600x1000 CSS pixels, and the viewer
 * window fits on the screen, where it has to be to be captured.
 *
 * Needs: xvfb-run (`sudo apt install xvfb`), ImageMagick's `import`,
 * `xwininfo` (x11-utils), python3 with libX11 (to size the viewer's
 * window), npm (for the extension build), and the checkout's .venv
 * (./scripts/gelb_bootstrap.sh). Running it twice
 * gives the same images, pixel for pixel. GELB_SHOTS_OUT=<folder> writes
 * them there instead of docs/user/figures (to compare).
 */

import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SELF = fileURLToPath(import.meta.url);
const REPO = path.resolve(path.dirname(SELF), '..');
const FIGURES = path.join(REPO, 'docs', 'user', 'figures');
const CODE = process.env.GELB_VSCODE || '/usr/share/code/code';
const EXAMPLE = path.join(REPO, 'examples', 'lbm', '2d', 'lid_driven_cavity_2d_bgk.gelb');
const SCREEN = { width: 3200, height: 2000 };
const SCALE = 2;
/** The one colour of every outline. */
const HIGHLIGHT = '#d9480f';

function die(message) {
    console.error(`gen_vscode_screenshots: ${message}`);
    process.exit(2);
}

/** Where the example's geometry block is, for the Problems shot (line
 *  and column numbers from 1): its first and last lines, and the `LID`
 *  of the lid's paint. */
const GEOMETRY = (() => {
    const lines = fs.readFileSync(EXAMPLE, 'utf8').split('\n');
    const first = lines.findIndex((l) => /^geometry\s*\{/.test(l));
    const last = lines.findIndex((l, i) => i > first && /^\}/.test(l));
    const lid = lines.findIndex((l, i) => i > first && i < last && /=\s*LID;/.test(l));
    if (first < 0 || last < 0 || lid < 0) die(`no geometry block with a LID paint in ${EXAMPLE}`);
    const column = lines[lid].indexOf('LID', lines[lid].indexOf('=')) + 1;
    return { first: first + 1, last: last + 1, lid: lid + 1, at: `${lid + 1}:${column}` };
})();

function onPath(cmd) {
    return spawnSync('sh', ['-c', `command -v ${cmd}`], { stdio: 'ignore' }).status === 0;
}

/** The environment of every child: none of the variables of a VS Code
 *  this may run inside (an integrated terminal) and no Wayland. */
function cleanEnv(extra = {}) {
    const env = {};
    for (const k of ['HOME', 'USER', 'LOGNAME', 'PATH', 'LANG', 'SHELL', 'TMPDIR',
        'DISPLAY', 'XAUTHORITY', 'GELB_VSCODE', 'GELB_SHOTS_OUT']) {
        if (process.env[k]) env[k] = process.env[k];
    }
    return { ...env, ...extra };
}

/* ------------------------------------------------------------------ */
/*  Outside the virtual display: check, install, re-run inside it     */
/* ------------------------------------------------------------------ */

function outer() {
    const keep = process.argv.includes('--keep');
    if (process.platform !== 'linux') die('this script runs on Linux (it needs xvfb).');
    if (!onPath('xvfb-run')) {
        die('xvfb-run not found. Install it (sudo apt install xvfb) and run again; '
            + 'the screenshots are never taken on the real display.');
    }
    for (const tool of ['import', 'xwininfo', 'python3', 'npm']) {
        if (!onPath(tool)) die(`${tool} not found (ImageMagick, x11-utils, python3, npm).`);
    }
    if (!fs.existsSync(CODE)) die(`VS Code not found at ${CODE} (set GELB_VSCODE).`);
    if (!fs.existsSync(path.join(REPO, '.venv', 'bin', 'gelb-view'))) {
        die('no .venv in the checkout: run ./scripts/gelb_bootstrap.sh first.');
    }
    // Short: VS Code's IPC socket lives in the user data folder.
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gvs-'));
    let failure;
    try {
        const ext = path.join(root, 'ext');
        console.log('Installing the extension into a throwaway extensions folder ...');
        const inst = spawnSync(path.join(REPO, 'scripts', 'install-vscode-ext.sh'),
            ['--extensions-dir', ext], { stdio: 'inherit', env: cleanEnv() });
        if (inst.status !== 0) {
            failure = 'the extension did not build or install.';
        } else {
            console.log('Taking the screenshots under xvfb ...');
            const r = spawnSync('xvfb-run', ['-a', '-s',
                `-screen 0 ${SCREEN.width}x${SCREEN.height}x24`, process.execPath, SELF],
            { stdio: 'inherit', env: cleanEnv({ GELB_SHOTS_ROOT: root }) });
            if (r.status !== 0) failure = 'taking the screenshots failed.';
        }
    } finally {
        if (keep) console.log(`Kept ${root}`);
        else fs.rmSync(root, { recursive: true, force: true });
    }
    if (failure) die(failure);
}

/* ------------------------------------------------------------------ */
/*  Inside the virtual display                                        */
/* ------------------------------------------------------------------ */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function inner(root) {
    const { _electron: electron } = createRequire(
        path.join(REPO, 'vscode-gelb', 'package.json'))('playwright-core');

    const ws = path.join(root, 'cavity');
    fs.mkdirSync(ws, { recursive: true });
    const file = path.join(ws, path.basename(EXAMPLE));
    fs.copyFileSync(EXAMPLE, file);
    const userData = path.join(root, 'ud');
    fs.mkdirSync(path.join(userData, 'User'), { recursive: true });
    fs.writeFileSync(path.join(userData, 'User', 'settings.json'), JSON.stringify({
        'workbench.colorTheme': 'Default Light Modern',
        'workbench.startupEditor': 'none',
        'workbench.tips.enabled': false,
        'workbench.statusBar.visible': false,
        'workbench.layoutControl.enabled': false,
        'workbench.secondarySideBar.defaultVisibility': 'hidden',
        'workbench.enableExperiments': false,
        'window.commandCenter': false,
        'window.restoreWindows': 'none',
        'chat.disableAIFeatures': true,
        'chat.commandCenter.enabled': false,
        'editor.fontSize': 15,
        'editor.minimap.enabled': false,
        'editor.stickyScroll.enabled': false,
        'editor.cursorBlinking': 'solid',
        'editor.renderLineHighlight': 'none',
        'editor.occurrencesHighlight': 'off',
        'editor.selectionHighlight': false,
        'breadcrumbs.enabled': false,
        'terminal.integrated.fontSize': 14,
        'git.enabled': false,
        'telemetry.telemetryLevel': 'off',
        'update.mode': 'none',
        'extensions.ignoreRecommendations': true,
        'security.workspace.trust.enabled': false,
        // The copy is outside the checkout, so the tools are named.
        'gelb.gelbcCommand': path.join(REPO, '.venv', 'bin', 'gelbc'),
        'gelb.gelbViewCommand': path.join(REPO, '.venv', 'bin', 'gelb-view'),
        'gelb.gelbRunCommand': path.join(REPO, 'scripts', 'gelb-run'),
    }, null, 2));

    const app = await electron.launch({
        executablePath: CODE,
        args: [
            '--user-data-dir', userData,
            '--extensions-dir', path.join(root, 'ext'),
            '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes',
            '--password-store=basic', '--ozone-platform=x11',
            `--force-device-scale-factor=${SCALE}`,
            ws, file,
        ],
        env: cleanEnv({ QT_SCALE_FACTOR: String(SCALE) }),
    });
    try {
        const win = await app.firstWindow();
        await app.evaluate(({ BrowserWindow }, s) => {
            const w = BrowserWindow.getAllWindows()[0];
            w.setPosition(0, 0);
            w.setSize(s.width, s.height);
        }, { width: SCREEN.width / SCALE, height: SCREEN.height / SCALE });
        await win.waitForSelector('.monaco-workbench .monaco-editor .view-lines', { timeout: 60000 });
        await sleep(3000);
        const shots = new Shots(app, win, process.env.GELB_SHOTS_OUT || FIGURES);
        await shots.injectStyle();
        await shots.assertNoChat();
        await shots.run(file);
    } finally {
        await app.close().catch(() => undefined);
    }
}

class Shots {
    constructor(app, win, out) {
        this.app = app;
        this.win = win;
        this.out = out;
    }

    async injectStyle() {
        await this.win.addStyleTag({ content: `
            .gelb-shot-hl {
                position: fixed; pointer-events: none; z-index: 100000;
                border: 2.5px solid ${HIGHLIGHT}; border-radius: 6px;
                box-sizing: border-box;
            }
            .monaco-editor .cursors-layer { visibility: hidden !important; }
            /* A spinning icon would be caught at a different angle each run. */
            *, *::before, *::after { animation: none !important; }
            .monaco-scrollable-element > .scrollbar,
            .monaco-editor .decorationsOverviewRuler { display: none !important; }
        ` });
    }

    /** The images show GeLB only: no Chat view, no secondary side bar. */
    async assertNoChat() {
        const visible = await this.win.evaluate(() => {
            const shown = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            return [...document.querySelectorAll(
                '.part.auxiliarybar, [id="workbench.panel.chat"], .interactive-session')]
                .some(shown);
        });
        if (visible) throw new Error('the Chat view or the secondary side bar is showing');
    }

    async resize(width, height) {
        await this.app.evaluate(({ BrowserWindow }, s) => {
            BrowserWindow.getAllWindows()[0].setSize(s.width, s.height);
        }, { width, height });
        await sleep(800);
    }

    async keys(...combos) {
        for (const k of combos) {
            await this.win.keyboard.press(k);
            await sleep(150);
        }
    }

    /** Run a command by its palette title. */
    async command(title) {
        await this.keys('F1');
        await this.win.keyboard.type(title);
        await sleep(600);
        await this.keys('Enter');
        await sleep(800);
    }

    async sideBar(visible) {
        const shown = await this.win.evaluate(() => {
            const el = document.querySelector('.part.sidebar');
            return !!el && el.getBoundingClientRect().width > 0;
        });
        if (shown !== visible) await this.keys('Control+B');
    }

    /** The visible editor lines: number -> bounding box. */
    async lines() {
        return this.win.evaluate(() => {
            const ed = document.querySelector('.part.editor .monaco-editor');
            const out = {};
            for (const el of ed.querySelectorAll('.line-numbers')) {
                const r = el.getBoundingClientRect();
                const n = Number(el.textContent.trim());
                if (n) out[n] = { x: r.x, y: r.y, width: r.width, height: r.height };
            }
            return out;
        });
    }

    /** Focus the editor's text input (the hidden cursor and the
     *  turned-off line highlight do not show where it is). */
    async focusEditor() {
        await this.win.locator('.part.editor .monaco-editor')
            .locator('.native-edit-context, textarea.inputarea').first().focus();
        await sleep(200);
    }

    /** Scroll the editor until `line` is its first visible line: from
     *  the top, one line per Ctrl+Down. */
    async scrollTo(line) {
        await this.focusEditor();
        await this.keys('Control+Home');
        for (let i = 1; i < line; i++) await this.win.keyboard.press('Control+ArrowDown');
        // A CodeLens takes room too: correct by single lines.
        for (let i = 0; i < 10; i++) {
            await sleep(300);
            const first = await this.firstLine();
            if (first === line) return;
            await this.win.keyboard.press(first < line ? 'Control+ArrowDown' : 'Control+ArrowUp');
        }
        throw new Error(`could not scroll to line ${line}`);
    }

    /** The first editor line shown whole. */
    async firstLine() {
        const top = (await this.rect('.part.editor .monaco-editor .view-lines')).y;
        const ls = await this.lines();
        return Math.min(...Object.keys(ls).map(Number).filter(n => ls[n].y >= top - 1));
    }

    /** Outline each rectangle (CSS pixels), with a little room. */
    async highlight(rects, pad = 3) {
        await this.win.evaluate(({ rects, pad }) => {
            for (const r of rects) {
                const d = document.createElement('div');
                d.className = 'gelb-shot-hl';
                Object.assign(d.style, {
                    left: `${r.x - pad}px`, top: `${r.y - pad}px`,
                    width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px`,
                });
                document.body.appendChild(d);
            }
        }, { rects, pad });
    }

    /** Cover `r` in the editor's background colour: a line cut in
     *  half at the edge of the editor reads as clutter. */
    async mask(r) {
        if (r.height <= 0) return;
        await this.win.evaluate((r) => {
            const bg = getComputedStyle(document.querySelector(
                '.part.editor .monaco-editor-background')).backgroundColor;
            const d = document.createElement('div');
            d.className = 'gelb-shot-hl gelb-shot-mask';
            Object.assign(d.style, {
                left: `${r.x}px`, top: `${r.y}px`, width: `${r.width}px`,
                height: `${r.height}px`, background: bg, border: 'none', borderRadius: '0',
            });
            document.body.appendChild(d);
        }, r);
    }

    async clearHighlights() {
        await this.win.evaluate(() => {
            for (const d of document.querySelectorAll('.gelb-shot-hl')) d.remove();
        });
    }

    async rect(selector) {
        const box = await this.win.locator(selector).first().boundingBox();
        if (!box) throw new Error(`not on screen: ${selector}`);
        return box;
    }

    /** Save the region `clip` (CSS pixels) as docs/user/figures/<name>. */
    async shoot(name, clip) {
        await this.assertNoChat();
        const c = {
            x: Math.max(0, Math.floor(clip.x)), y: Math.max(0, Math.floor(clip.y)),
            width: Math.ceil(clip.width), height: Math.ceil(clip.height),
        };
        await this.win.screenshot({ path: path.join(this.out, name), clip: c });
        console.log(`  ${name}: ${c.width * SCALE}x${c.height * SCALE}`);
    }

    async run(file) {
        this.fileName = path.basename(file);
        await this.editorShot();
        await this.problemsShot();
        await this.previewShot();
        await this.runShots();
    }

    /** GeLB: Show Source Preview, beside the editor. */
    async previewShot() {
        // Wide enough for the whole 65x65 grid beside its legend (the
        // preview clips a grid wider than its column, for pan and zoom).
        await this.sideBar(false);
        await this.resize(SCREEN.width / SCALE, 760);
        await this.win.locator('.part.editor a.action-label[aria-label="GeLB: Show Source Preview"]').click();
        // The webview's document: the one with the preview's canvas and
        // a filled legend (gelb-view has answered).
        let frame;
        for (let i = 0; i < 120 && !frame; i++) {
            for (const f of this.win.frames()) {
                if (f === this.win.mainFrame()) continue;
                const ready = await f.evaluate(() => !!document.getElementById('mainCanvas')
                    && !!document.querySelector('#legend *')).catch(() => false);
                if (ready) frame = f;
            }
            if (!frame) await sleep(500);
        }
        if (!frame) throw new Error('the preview did not draw');
        await sleep(1500);
        const groups = await this.win.locator('.part.editor .editor-group-container').all();
        const group = await groups[groups.length - 1].boundingBox();
        const canvas = await frame.locator('#mainCanvas').boundingBox();
        const legend = await frame.locator('#legend').boundingBox();
        // The grid and the legend's entries; not the empty rest. (Inside
        // the frame, sizes are measured from the legend's own left edge.)
        const entriesWidth = await frame.evaluate(() => {
            const legend = document.getElementById('legend');
            const left = legend.getBoundingClientRect().left;
            const walk = document.createTreeWalker(legend, NodeFilter.SHOW_TEXT);
            let right = 0;
            for (let n = walk.nextNode(); n; n = walk.nextNode()) {
                const r = document.createRange();
                r.selectNodeContents(n);
                right = Math.max(right, r.getBoundingClientRect().right - left);
            }
            return right;
        });
        await this.shoot('vscode_preview.png', {
            x: group.x, y: group.y,
            width: Math.min(group.width, legend.x + entriesWidth + 24 - group.x),
            height: canvas.y + canvas.height + 12 - group.y,
        });
        // Close the preview: close everything and reopen the file alone.
        await this.command('View: Close All Editor Groups');
        await this.keys('Control+P');
        await this.win.keyboard.type(this.fileName);
        await sleep(800);
        await this.keys('Enter');
        await this.win.waitForSelector('.part.editor .monaco-editor .view-lines');
        await sleep(1000);
    }

    /** The Run view with a run going, and the viewer that run opened. */
    async runShots() {
        await this.resize(1100, 760);
        await this.win.locator('.activitybar [aria-label="GeLB"]').first().click();
        await sleep(1000);
        for (const name of ['Program Structure', 'Other Diagnostics']) {
            const header = this.win.locator(`.pane-header[aria-label^="${name}"]`);
            if ((await header.getAttribute('aria-expanded')) === 'true') await header.click();
            await sleep(300);
        }
        await sleep(500);
        const row = (tip) => this.win.locator(`.monaco-list-row[aria-label^="${tip}"]`).first();
        await row('Save the file and run it').click();
        const status = row('The current or last run');
        for (let i = 0; i < 600; i++) {
            if (/running/.test(await status.textContent())) break;
            await sleep(500);
        }
        // Narrower than it opens, so that its text stays readable in print.
        const viewer = this.resizeWindow(await this.waitForViewer(), 840 * SCALE, 600 * SCALE);
        await sleep(3000);
        const pane = await this.rect('.pane:has(.pane-header[aria-label^="Run"])');
        const lastRow = await this.win.locator('.pane:has(.pane-header[aria-label^="Run"]) .monaco-list-row').last().boundingBox();
        await this.highlight([await row('Save the file and run it').boundingBox(), await status.boundingBox()], 1);
        await this.shoot('vscode_run.png', {
            x: pane.x, y: pane.y, width: pane.width,
            height: lastRow.y + lastRow.height + 6 - pane.y,
        });
        await this.clearHighlights();
        this.grabWindow(viewer, 'vscode_gelb_view.png');
        await row('Stop the run').click();
        for (let i = 0; i < 60; i++) {
            if (/stopped|finished/.test(await status.textContent())) break;
            await sleep(500);
        }
    }

    /** The geometry of the viewer's top-level window, once it is mapped. */
    async waitForViewer() {
        for (let i = 0; i < 600; i++) {
            const tree = execFileSync('xwininfo', ['-root', '-tree']).toString();
            const wins = tree.split('\n')
                .filter(l => /"gelb-view"/.test(l))
                .map(l => /(0x[0-9a-f]+).*?(\d+)x(\d+)\+-?\d+\+-?\d+\s+\+(-?\d+)\+(-?\d+)/.exec(l))
                .filter(Boolean)
                .map(m => ({ id: m[1], width: +m[2], height: +m[3], x: +m[4], y: +m[5] }))
                .filter(w => w.width > 200 && w.height > 200)
                .sort((a, b) => b.width * b.height - a.width * a.height);
            if (wins.length) return wins[0];
            await sleep(500);
        }
        throw new Error('the viewer did not open');
    }

    /** Give the viewer's window the size `w`x`h` (screen pixels) at the
     *  top left: there is no window manager to ask, so through Xlib. */
    resizeWindow(viewer, w, h) {
        execFileSync('python3', ['-c', `
import ctypes
x = ctypes.cdll.LoadLibrary('libX11.so.6')
x.XOpenDisplay.restype = ctypes.c_void_p
d = ctypes.c_void_p(x.XOpenDisplay(None))
x.XMoveResizeWindow(d, ctypes.c_ulong(${parseInt(viewer.id, 16)}), 0, 0, ${w}, ${h})
x.XFlush(d)
x.XCloseDisplay(d)
`]);
        return { ...viewer, x: 0, y: 0, width: w, height: h };
    }

    /** Save the X window at `g` (screen pixels) from a grab of the screen. */
    grabWindow(g, name) {
        const out = path.join(this.out, name);
        execFileSync('import', ['-window', 'root', '-crop',
            `${g.width}x${g.height}+${g.x}+${g.y}`, '+repage', out]);
        console.log(`  ${name}: ${g.width}x${g.height}`);
    }

    /** The example open: highlighting, the CodeLens and the title buttons. */
    async editorShot() {
        await this.sideBar(false);
        await this.resize(760, 640);
        await this.scrollTo(17);
        const ls = await this.lines();
        const editor = await this.rect('.part.editor');
        const lens = await this.rect('.part.editor .codelens-decoration');
        const runButton = await this.rect('.part.editor a.action-label[aria-label="Run"]');
        const preview = await this.rect('.part.editor a.action-label[aria-label="GeLB: Show Source Preview"]');
        await this.highlight([
            lens,
            { x: runButton.x, y: runButton.y, width: preview.x + preview.width - runButton.x,
                height: Math.max(runButton.height, preview.height) },
        ]);
        await this.shoot('vscode_editor.png', {
            x: editor.x, y: editor.y, width: editor.width,
            height: ls[28].y - editor.y,
        });
        await this.clearHighlights();
    }

    /** A misspelt node class, saved: the squiggle and the Problems entry. */
    async problemsShot() {
        await this.resize(760, 600);
        // `LID` -> `LDI` in the lid's paint, then save: gelbc reads the
        // file from disk.
        await this.focusEditor();
        await this.command('Go to Line/Column');
        await this.win.keyboard.type(GEOMETRY.at);
        await this.keys('Enter', 'Shift+ArrowRight', 'Shift+ArrowRight', 'Shift+ArrowRight');
        await this.win.keyboard.type('LDI');
        await this.keys('Control+S');
        await this.win.waitForSelector('.part.editor .squiggly-error', { timeout: 60000 });
        await this.command('View: Focus Problems');
        await this.win.waitForSelector('.markers-panel .monaco-list-row', { timeout: 30000 });
        // A window just tall enough: the editor ends below the block.
        let height = 600;
        for (let i = 0; i < 4; i++) {
            await this.scrollTo(GEOMETRY.first);
            await this.keys('Escape');
            await sleep(500);
            const l = await this.lines();
            const end = l[GEOMETRY.last];
            const gap = (await this.rect('.part.panel')).y - (end.y + end.height);
            if (gap < 40) break;
            height = Math.round(height - (gap - 24));
            await this.resize(760, height);
        }
        const ls = await this.lines();
        const editor = await this.rect('.part.editor');
        const squiggle = await this.rect('.part.editor .squiggly-error');
        const entry = await this.rect('.markers-panel .monaco-list-row:nth-child(2)');
        const below = ls[GEOMETRY.last].y + ls[GEOMETRY.last].height;
        await this.mask({ x: editor.x, y: below, width: editor.width,
            height: (await this.rect('.part.panel')).y - below });
        await this.highlight([
            { x: squiggle.x, y: ls[GEOMETRY.lid].y, width: squiggle.width,
                height: ls[GEOMETRY.lid].height },
            entry,
        ]);
        await this.shoot('vscode_problems.png', {
            x: editor.x, y: ls[GEOMETRY.first].y,
            width: editor.width, height: entry.y + entry.height + 10 - ls[GEOMETRY.first].y,
        });
        await this.clearHighlights();
        // Back to the example as it is, saved and clean.
        await this.focusEditor();
        await this.command('Go to Line/Column');
        await this.win.keyboard.type(GEOMETRY.at);
        await this.keys('Enter', 'Shift+ArrowRight', 'Shift+ArrowRight', 'Shift+ArrowRight');
        await this.win.keyboard.type('LID');
        await this.keys('Control+S');
        await this.win.waitForSelector('.part.editor .squiggly-error',
            { state: 'detached', timeout: 60000 });
        await this.command('View: Close Panel');
    }
}

if (process.env.GELB_SHOTS_ROOT) {
    inner(process.env.GELB_SHOTS_ROOT).catch((e) => {
        console.error(e);
        process.exit(1);
    });
} else {
    outer();
}
