/**
 * GeLB VSCode extension — runtime entry.
 *
 * Adds two commands:
 *   - "GeLB: Show Source Preview" — opens a webview alongside the editor
 *     showing the geometry + stencils, refreshed on save.
 *   - "GeLB: Lint Geometry" — runs the geometry-lint warnings and shows
 *     them as VSCode notifications.
 *
 * Both commands shell out to `gelb-view` (or whatever
 * `gelb.gelbViewCommand` is configured to).
 *
 * The sidebar's Run view, its "GeLB: Run" command and the Run CodeLens
 * live in runView.ts; this file feeds it the same active document as
 * Program Structure.
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { ProgramStructureProvider } from './programStructureView';
import { reportMissingTool, toolCommand } from './toolCommand';
import { RunProvider } from './runView';
import { widenToWord } from './diagnosticRange';
import {
    GelbDocumentSymbolProvider,
    GelbWorkspaceSymbolProvider,
} from './symbolProviders';

let activeInteractive: InteractivePreview | undefined;
let gelbDiagnostics: vscode.DiagnosticCollection | undefined;
// Module-scope so showSourcePreview / showInteractivePreview can
// pin the sidebar's Program Structure view to the previewed file.
let programStructureProvider: ProgramStructureProvider | undefined;
let runProvider: RunProvider | undefined;

export function activate(context: vscode.ExtensionContext) {
    gelbDiagnostics = vscode.languages.createDiagnosticCollection('gelb');
    context.subscriptions.push(gelbDiagnostics);

    // "Program Structure" TreeView in the GeLB Activity-Bar container.
    //
    // The module-scope `programStructureProvider` is `| undefined`
    // because activate() may not have run yet at module-evaluation
    // time; inside this function we know it's defined, so we alias
    // it to a non-nullable local and use that in the closures below
    // to keep TypeScript's strict-null narrowing happy.
    const provider = new ProgramStructureProvider();
    programStructureProvider = provider;
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider(
            'gelbProgramStructure', provider,
        ),
    );

    // "Run" TreeView, CodeLens and the gelb.run* commands. It follows
    // the same document as Program Structure (one document, two views).
    const run = new RunProvider(context);
    runProvider = run;
    context.subscriptions.push(...run.register());

    // DocumentSymbolProvider → Outline pane, breadcrumbs, ⌘⇧O.
    // WorkspaceSymbolProvider → ⌘T across all .gelb files.
    context.subscriptions.push(
        vscode.languages.registerDocumentSymbolProvider(
            { language: 'gelb' },
            new GelbDocumentSymbolProvider(),
        ),
        vscode.languages.registerWorkspaceSymbolProvider(
            new GelbWorkspaceSymbolProvider(),
        ),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand(
            'gelb.showInteractivePreview',
            () => showInteractivePreview(context)
        ),
        vscode.commands.registerCommand(
            'gelb.lintGeometry',
            () => lintGeometry()
        ),
        // Refresh the tree when the active editor changes. If the new
        // active editor is a .gelb file, pin the sidebar to it so
        // subsequent focus changes (including onto the preview
        // webview, which has no text editor) don't blank the view.
        vscode.window.onDidChangeActiveTextEditor((editor) => {
            if (editor && editor.document.languageId === 'gelb') {
                provider.setCurrentDocument(editor.document);
                run.setCurrentDocument(editor.document);
            } else {
                // Non-gelb editor (or none) focused — keep the sticky
                // currentDocument so the sidebar still shows the last
                // .gelb we were looking at (helpful when the preview
                // is focused in another column).
                provider.refresh();
                run.refresh();
            }
        }),
        // Refresh when the user types in the .gelb file the sidebar
        // is currently showing; debounced so the parser doesn't run
        // on every keystroke. Checks against the sticky
        // currentDocument rather than the active editor so edits
        // still propagate while the webview has focus.
        vscode.workspace.onDidChangeTextDocument((e) => {
            if (e.document.languageId !== 'gelb') return;
            const cur = provider.getCurrentDocument();
            if (cur && cur.uri.toString() === e.document.uri.toString()) {
                provider.refreshDebounced();
            }
            const runCur = run.getCurrentDocument();
            if (runCur && runCur.uri.toString() === e.document.uri.toString()) {
                run.refreshDebounced();
            }
        }),
        vscode.workspace.onDidSaveTextDocument((doc) => {
            if (doc.languageId !== 'gelb') return;
            const cfg = vscode.workspace.getConfiguration('gelb');
            // Re-run the Problems-panel diagnostics if enabled (default on).
            if (cfg.get<boolean>('lintOnSave', true)) {
                scheduleDiagnostics(doc);
            }
            if (!cfg.get<boolean>('refreshOnSave', true)) return;
            if (activeInteractive && activeInteractive.document.uri.toString()
                === doc.uri.toString()) {
                activeInteractive.refresh();
            }
        }),
        vscode.workspace.onDidOpenTextDocument((doc) => {
            if (doc.languageId !== 'gelb') return;
            const cfg = vscode.workspace.getConfiguration('gelb');
            if (cfg.get<boolean>('lintOnOpen', true)) {
                scheduleDiagnostics(doc);
            }
        }),
        vscode.workspace.onDidCloseTextDocument((doc) => {
            if (doc.languageId !== 'gelb') return;
            gelbDiagnostics?.delete(doc.uri);
            diagnosticRunState.delete(doc.uri.toString());
            // If the closed file is the one the sidebar is pinned to,
            // drop the pin — leaving it pointing at a closed document
            // would be misleading.
            const cur = provider.getCurrentDocument();
            if (cur && cur.uri.toString() === doc.uri.toString()) {
                provider.setCurrentDocument(undefined);
            }
            const runCur = run.getCurrentDocument();
            if (runCur && runCur.uri.toString() === doc.uri.toString()) {
                run.setCurrentDocument(undefined);
            }
        }),
    );

    // Lint any .gelb files that were already open when the extension
    // activated — otherwise they stay un-diagnosed until next save.
    const cfg = vscode.workspace.getConfiguration('gelb');
    if (cfg.get<boolean>('lintOnOpen', true)) {
        for (const doc of vscode.workspace.textDocuments) {
            if (doc.languageId === 'gelb') scheduleDiagnostics(doc);
        }
    }
}

export function deactivate() {}

/* ---------- Problems-panel diagnostics ---------- */

// Per-URI throttling. We run at most one gelbc invocation per file
// concurrently; if another save/open fires while one is in flight,
// we remember that and rerun once the current one finishes.
interface RunState { inFlight: boolean; pending: boolean; }
const diagnosticRunState = new Map<string, RunState>();

interface GelbDiagnosticJson {
    severity: 'error' | 'warning';
    message: string;
    hint?: string | null;
    source?: string;
    range: {
        startLine: number;
        startCol: number;
        endLine: number;
        endCol: number;
    };
}

function scheduleDiagnostics(doc: vscode.TextDocument) {
    if (!gelbDiagnostics) return;
    const key = doc.uri.toString();
    const st = diagnosticRunState.get(key) ?? { inFlight: false, pending: false };
    if (st.inFlight) {
        st.pending = true;
        diagnosticRunState.set(key, st);
        return;
    }
    st.inFlight = true;
    st.pending = false;
    diagnosticRunState.set(key, st);
    runDiagnostics(doc).finally(() => {
        const after = diagnosticRunState.get(key);
        if (!after) return;
        after.inFlight = false;
        if (after.pending) {
            after.pending = false;
            scheduleDiagnostics(doc);
        }
    });
}

async function runDiagnostics(doc: vscode.TextDocument): Promise<void> {
    if (!gelbDiagnostics) return;
    const tool = toolCommand('gelbc', doc.uri);
    if (!tool.argv) {
        const diag = new vscode.Diagnostic(
            new vscode.Range(0, 0, 0, 1),
            `GeLB diagnostics disabled for this file — ${tool.error}.`,
            vscode.DiagnosticSeverity.Warning);
        diag.source = 'gelb';
        gelbDiagnostics.set(doc.uri, [diag]);
        return;
    }
    const [exe = '', ...cmdArgs] = tool.argv;
    const cmd = tool.argv.join(' ');
    const args = [...cmdArgs, doc.fileName, '--diagnostics-json'];
    const wsFolder = vscode.workspace.getWorkspaceFolder(doc.uri);
    const cwd = wsFolder?.uri.fsPath ?? path.dirname(doc.fileName);

    interface SpawnResult {
        stdout: string;
        stderr: string;
        code: number | null;
        spawnError: Error | null;
    }
    const result = await new Promise<SpawnResult>((resolve) => {
        const proc = cp.spawn(exe, args, { cwd });
        let stdout = '', stderr = '';
        proc.stdout.on('data', (d) => { stdout += d.toString(); });
        proc.stderr.on('data', (d) => { stderr += d.toString(); });
        proc.on('error', (e) => resolve(
            { stdout, stderr, code: null, spawnError: e }));
        proc.on('close', (code) => resolve(
            { stdout, stderr, code, spawnError: null }));
    });

    // Try to parse the JSON. If that works we trust it regardless of exit
    // code (exit 1 is expected when there are errors in the file).
    let parsed: GelbDiagnosticJson[] | null = null;
    if (result.stdout.trim()) {
        try {
            const payload = JSON.parse(result.stdout);
            if (Array.isArray(payload?.diagnostics)) {
                parsed = payload.diagnostics as GelbDiagnosticJson[];
            }
        } catch { /* fall through to setup-problem path */ }
    }

    const diags: vscode.Diagnostic[] = [];
    if (parsed !== null) {
        for (const d of parsed) {
            const r = d.range
                ?? { startLine: 0, startCol: 0, endLine: 0, endCol: 1 };
            const startLine = Math.max(0, r.startLine);
            let startCol = Math.max(0, r.startCol);
            let endCol = Math.max(0, r.endCol);
            if (r.endLine === r.startLine && startLine < doc.lineCount) {
                [startCol, endCol] = widenToWord(
                    doc.lineAt(startLine).text, startCol, endCol);
            }
            const range = new vscode.Range(
                startLine, startCol, Math.max(0, r.endLine), endCol);
            const sev = d.severity === 'error'
                ? vscode.DiagnosticSeverity.Error
                : vscode.DiagnosticSeverity.Warning;
            const full = d.hint ? `${d.message}\n${d.hint}` : d.message;
            const diag = new vscode.Diagnostic(range, full, sev);
            diag.source = d.source ?? 'gelbc';
            diags.push(diag);
        }
    } else {
        // gelbc never produced a parseable JSON document — almost always
        // a mis-configured gelbcCommand. Surface a clear setup warning
        // at the top of the file so the user has something actionable.
        // Warning (not error) so we don't accidentally block preview on
        // a purely-tooling issue.
        let detail: string;
        if (result.spawnError) {
            detail = `could not spawn "${cmd}" (${result.spawnError.message})`;
        } else if ((result.code ?? 0) !== 0) {
            const stderrTail = result.stderr.trim().slice(-200);
            detail = `"${cmd}" exited with code ${result.code}` +
                (stderrTail ? `; stderr: ${stderrTail}` : '');
        } else {
            detail = `"${cmd}" produced no JSON output`;
        }
        const msg =
            `GeLB diagnostics disabled for this file — ${detail}.\n` +
            `Set "gelb.gelbcCommand" to the command that runs gelbc ` +
            `(for example "uv run gelbc"), or leave it empty to use the ` +
            `gelbc of the GeLB source checkout or installation the file ` +
            `is in.`;
        const diag = new vscode.Diagnostic(
            new vscode.Range(0, 0, 0, 1), msg,
            vscode.DiagnosticSeverity.Warning);
        diag.source = 'gelb';
        diags.push(diag);
    }
    gelbDiagnostics.set(doc.uri, diags);
}

async function blockedByErrors(
    doc: vscode.TextDocument,
): Promise<boolean> {
    if (!gelbDiagnostics) return false;
    // If diagnostics haven't run yet for this file (e.g. user opened
    // preview immediately), run them synchronously first.
    if (gelbDiagnostics.get(doc.uri) === undefined
        || gelbDiagnostics.get(doc.uri)!.length === 0
        && !diagnosticRunState.get(doc.uri.toString())) {
        await runDiagnostics(doc);
    }
    const diags = gelbDiagnostics.get(doc.uri) ?? [];
    const errors = diags.filter(
        d => d.severity === vscode.DiagnosticSeverity.Error);
    if (errors.length === 0) return false;
    vscode.window.showErrorMessage(
        `GeLB: fix ${errors.length} compile error` +
        (errors.length === 1 ? '' : 's') +
        ' before previewing (see the Problems panel).'
    );
    return true;
}




/* ---------- Lint Geometry ---------- */

async function lintGeometry() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== 'gelb') {
        vscode.window.showErrorMessage(
            'Open a .gelb file first, then run this command.');
        return;
    }
    const tool = toolCommand('gelb-view', editor.document.uri);
    if (!tool.argv) {
        await reportMissingTool('gelb-view', tool.error);
        return;
    }
    const [exe = '', ...cmdArgs] = tool.argv;
    const args = [...cmdArgs, 'source', editor.document.fileName, '--lint'];

    try {
        const output = await new Promise<string>((resolve, reject) => {
            const proc = cp.spawn(exe, args);
            let buf = '';
            proc.stdout.on('data', (d) => { buf += d.toString(); });
            proc.stderr.on('data', (d) => { buf += d.toString(); });
            proc.on('error', (e) => reject(e));
            proc.on('close', () => resolve(buf));
        });
        if (output.trim().includes('No geometry-lint warnings.')) {
            vscode.window.showInformationMessage(
                'GeLB: no geometry-lint warnings.');
        } else {
            vscode.window.showWarningMessage(
                'GeLB geometry-lint warnings (see Output: GeLB).');
            const channel = vscode.window.createOutputChannel('GeLB');
            channel.show(true);
            channel.appendLine(output);
        }
    } catch (err: any) {
        vscode.window.showErrorMessage(
            `GeLB lint failed: ${err.message}`);
    }
}


function escapeHtml(s: string): string {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}


/* ---------- Interactive Preview Webview ---------- */

class InteractivePreview {
    panel: vscode.WebviewPanel;
    document: vscode.TextDocument;
    extensionUri: vscode.Uri;
    tmpJson: string;

    constructor(
        document: vscode.TextDocument,
        extensionUri: vscode.Uri,
    ) {
        this.document = document;
        this.extensionUri = extensionUri;
        this.tmpJson = path.join(
            os.tmpdir(),
            `gelb-interactive-${process.pid}-${Date.now()}.json`
        );

        this.panel = vscode.window.createWebviewPanel(
            'gelbInteractivePreview',
            `GeLB Interactive: ${path.basename(document.fileName)}`,
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.joinPath(extensionUri, 'media'),
                ],
            }
        );

        this.panel.onDidDispose(() => {
            if (activeInteractive === this) {
                activeInteractive = undefined;
            }
            try { fs.unlinkSync(this.tmpJson); } catch (e) { /* ignore */ }
        });
    }

    async refresh() {
        const cfg = vscode.workspace.getConfiguration('gelb');
        const tool = toolCommand('gelb-view', this.document.uri);
        if (!tool.argv) {
            this.panel.webview.html = this._errorHtml(`${tool.error}.`);
            return;
        }
        const [exe = '', ...cmdArgs] = tool.argv;
        const args = [
            ...cmdArgs,
            'source',
            this.document.fileName,
            '--export-json', this.tmpJson,
        ];

        this.panel.webview.html = this._loadingHtml();

        try {
            await this._runCommand(exe, args);
            const json = fs.readFileSync(this.tmpJson, 'utf-8');
            const doc = JSON.parse(json);
            const ndim = doc?.geometry?.ndim;
            const stencilAnimMs = Math.max(500, Math.min(15000,
                cfg.get<number>('stencilAnimationDurationMs', 3000)));
            if (ndim === 3) {
                const mediaRoot = vscode.Uri.joinPath(
                    this.extensionUri, 'media');
                const threeUri = this.panel.webview.asWebviewUri(
                    vscode.Uri.joinPath(mediaRoot, 'three.module.min.js'));
                const controlsUri = this.panel.webview.asWebviewUri(
                    vscode.Uri.joinPath(mediaRoot, 'OrbitControls.js'));
                this.panel.webview.html = this._renderHtml3D(
                    json,
                    threeUri.toString(),
                    controlsUri.toString(),
                    this.panel.webview.cspSource,
                    stencilAnimMs,
                );
            } else {
                this.panel.webview.html = this._renderHtml2D(
                    json, stencilAnimMs);
            }
        } catch (err: any) {
            this.panel.webview.html = this._errorHtml(
                String(err?.message ?? err));
        }
    }

    _runCommand(exe: string, args: string[]): Promise<void> {
        return new Promise((resolve, reject) => {
            const wsFolder = vscode.workspace.getWorkspaceFolder(
                this.document.uri);
            const cwd = wsFolder?.uri.fsPath
                ?? path.dirname(this.document.fileName);
            const proc = cp.spawn(exe, args, { cwd });
            let stderr = '';
            proc.stderr.on('data', (d) => { stderr += d.toString(); });
            proc.on('error', (e) => reject(new Error(
                `Failed to spawn ${exe}: ${e.message}`)));
            proc.on('close', (code) => {
                if (code !== 0) {
                    reject(new Error(
                        `${exe} exited with code ${code}\n\n${stderr}`));
                } else {
                    resolve();
                }
            });
        });
    }

    _loadingHtml(): string {
        return `<!DOCTYPE html><html><body style="font-family: sans-serif">
            <p>Resolving geometry…</p></body></html>`;
    }

    _errorHtml(err: string): string {
        return `<!DOCTYPE html>
<html><body style="font-family: var(--vscode-font-family); padding: 8px;">
    <h3 style="color: var(--vscode-errorForeground);">GeLB interactive preview failed</h3>
    <pre style="background: var(--vscode-textCodeBlock-background); padding: 8px; white-space: pre-wrap;">${escapeHtml(err)}</pre>
</body></html>`;
    }

    _renderHtml2D(jsonStr: string, stencilAnimMs: number): string {
        // Embed the JSON directly as a JS literal so the webview has
        // zero round-trips on hover/click.
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<style>
  body { font-family: var(--vscode-font-family); margin: 0; padding: 8px;
         color: var(--vscode-foreground);
         background: var(--vscode-editor-background); }
  #wrap { display: grid; grid-template-columns: 1fr 280px; gap: 12px; }
  /* max-height caps the wrap so that a large canvas (e.g. 256×256 at
     CELL=3 → 768×768) does not push the bottom-pinned axis gizmo below
     the viewport. Pan/zoom already lets the user navigate oversized
     canvases inside this clipped region. */
  #canvasWrap { position: relative; border: 1px solid var(--vscode-panel-border);
                background: var(--vscode-editor-background); overflow: hidden;
                display: flex; justify-content: center; align-items: center;
                min-height: 120px; max-height: calc(100vh - 110px);
                touch-action: none; }
  #canvasInner { position: relative; transform-origin: 0 0;
                 will-change: transform; }
  #canvasInner.smooth { transition: transform 250ms ease-out; }
  /* image-rendering: auto asks the browser to use smooth (bilinear)
     interpolation when the CSS transform scales the canvas to a
     non-integer ratio. pixelated / nearest-neighbour would pop every
     source pixel into hard display-pixel squares, producing moiré
     bands that interact with the inter-node gaps — a known
     photosensitivity trigger. */
  #mainCanvas { display: block; image-rendering: auto;
                cursor: crosshair; }
  #viewToolbar { display: flex; align-items: center; gap: 4px;
                 padding: 2px 0 4px 0; font-size: 11px;
                 color: var(--vscode-descriptionForeground); }
  #viewToolbar button { font-size: 11px; padding: 1px 8px;
                background: var(--vscode-button-secondaryBackground, transparent);
                color: var(--vscode-button-secondaryForeground, inherit);
                border: 1px solid var(--vscode-panel-border);
                cursor: pointer; }
  #viewToolbar button:hover {
                background: var(--vscode-button-secondaryHoverBackground,
                                    var(--vscode-list-hoverBackground)); }
  #zoomLabel { font-family: monospace; min-width: 48px; text-align: right; }
  /* Thin yellow wireframe outlines matching the 3D view: soft amber for
     hover, bright yellow for selection. The element has (width, height)
     = (nodeW, nodeH) with a transparent background; the CSS outline is
     drawn just outside its footprint, so the node colour underneath is
     never covered and the outline ring is geometrically centred on the
     node — for any CELL size. */
  #cellHover { position: absolute; pointer-events: none;
               outline: 1px solid #ffc266;
               display: none; }
  #cellSelected { position: absolute; pointer-events: none;
                  outline: 2px solid #ffdd00;
                  display: none; }
  /* Translucent squares overlaid on read / write target cells during the
     Space-triggered stencil animation. Positioned + sized exactly like
     the hover/selected overlays (hugging the node), with opacity driven
     per-frame from JS. */
  .stencilTarget { position: absolute; pointer-events: none;
                   box-sizing: border-box; opacity: 0; }
  #side { font-size: 11px; }
  #side h3 { font-size: 12px; margin: 0 0 6px 0; }
  #side h4 { font-size: 11px; margin: 8px 0 4px 0;
             border-bottom: 1px solid var(--vscode-panel-border); }
  .nc-swatch { display: inline-block; width: 10px; height: 10px;
               vertical-align: middle; margin-right: 4px;
               border: 1px solid #555; }
  .legend-row { padding: 1px 0; }
  table { border-collapse: collapse; font-size: 10px; }
  td { padding: 1px 6px 1px 0; vertical-align: top; }
  td.k { color: var(--vscode-descriptionForeground); }
  /* Reads/writes text colour matches the stencil-animation overlay colour
     one-to-one, so the side-panel table reads as the same information
     the on-screen fade-in is showing. */
  .reads td { color: #2979ff; }
  .writes td { color: #e53935; }
  .stencil-block { margin-bottom: 6px; }
  #axisGizmo { position: absolute; left: 6px; bottom: 6px;
               width: 72px; height: 72px;
               pointer-events: none; z-index: 10; }
  #axisGizmo svg { width: 100%; height: 100%; overflow: visible; }
  #status { font-family: monospace; font-size: 10px;
            color: var(--vscode-descriptionForeground);
            min-height: 14px; padding: 2px 0; }
  #blockSelect { width: 100%; font-size: 11px; padding: 2px;
                 background: var(--vscode-input-background);
                 color: var(--vscode-input-foreground);
                 border: 1px solid var(--vscode-input-border); }
</style>
</head>
<body>
<div id="status">Hover to inspect · Click to select · Space = stencil animation · Wheel = zoom · Alt-drag = pan.</div>
<div id="viewToolbar">
  <button id="btnFit" title="Reset view (0)">Fit</button>
  <button id="btnZoomOut" title="Zoom out (-)">−</button>
  <button id="btnZoomIn" title="Zoom in (+)">+</button>
  <span id="zoomLabel">100%</span>
</div>
<div id="wrap">
  <div id="canvasWrap">
    <div id="canvasInner">
      <canvas id="mainCanvas"></canvas>
      <div id="cellHover"></div>
      <div id="cellSelected"></div>
    </div>
    <div id="axisGizmo"></div>
  </div>
  <div id="side">
    <h3 id="title"></h3>
    <div id="info"></div>
    <h4>Legend</h4>
    <div id="legend"></div>
    <h4>Blocks (click cell first)</h4>
    <select id="blockSelect"></select>
    <div id="stencils"></div>
  </div>
</div>

<script>
'use strict';
console.log('GeLB interactive view 2D/1D: build 2026-04-19l (source-like DF notation)');
// Total stencil-animation duration (ms). Configured via the
// "gelb.stencilAnimationDurationMs" setting; embedded here by the host.
const STENCIL_ANIM_MS = ${stencilAnimMs};

// ===== Embedded data =====
const DATA = ${jsonStr};

// ===== Decode nc_map from base64 → Int32Array =====
function decodeNcMap(g) {
  const bin = atob(g.nc_map_b64);
  const buf = new ArrayBuffer(bin.length);
  const u8 = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new Int32Array(buf);
}

const geo = DATA.geometry;
const sten = DATA.stencils;
const nc_map = decodeNcMap(geo);
// nc_map is C-contiguous with shape matching geo.nc_map_shape (1-3 dims).
// 1D: flat[x]. 2D: flat[x*Ny + y]. 3D: flat[(x*Ny + y)*Nz + z].
const ndim = geo.ndim;
const Nx = geo.nc_map_shape[0];
const Ny = ndim >= 2 ? geo.nc_map_shape[1] : 1;
const Nz = ndim >= 3 ? geo.nc_map_shape[2] : 1;
let zSlice = Math.floor(Nz / 2);

function ncAt(x, y) {
  if (x < 0 || x >= Nx || y < 0 || y >= Ny) return -1;
  if (ndim === 1) return nc_map[x];
  if (ndim === 2) return nc_map[x * Ny + y];
  return nc_map[(x * Ny + y) * Nz + zSlice];
}

// ===== Colour palette (matches the Python side) =====
const PALETTE = [
  '#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3',
  '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3',
  '#1b9e77', '#d95f02'
];

const ncColours = geo.nc_order.map((_, i) => PALETTE[i % PALETTE.length]);

// ===== Compute cell counts =====
const ncCounts = new Map();
for (const name of geo.nc_order) ncCounts.set(name, 0);
const total = nc_map.length;
for (let i = 0; i < total; i++) {
  const id = nc_map[i];
  if (id >= 1 && id <= geo.nc_order.length) {
    const name = geo.nc_order[id - 1];
    ncCounts.set(name, (ncCounts.get(name) || 0) + 1);
  }
}

// ===== Render geometry to canvas =====
const canvas = document.getElementById('mainCanvas');
const ctx = canvas.getContext('2d');

// Sizing: aim for the largest cellSize that fits within ~900x520 px.
// 1D strips stretch vertically so cells stay clickable even when Nx is huge.
// CELL must be at least 5 so (i) drawGeometry can leave a 1-px margin on
// each side of the node AND (ii) each node has a 3×3 pixel core, which
// stays recognisable after bilinear smoothing (a 1×1 node would blur
// into a faint halo at any non-integer zoom). For dense grids (e.g.
// 256×256 Gray-Scott) the canvas then overflows the wrap; pan
// (Alt-drag) + wheel-zoom handle navigation inside the clipped region.
const MIN_CELL = 5;
function computeCellSize() {
  const wrap = document.getElementById('canvasWrap');
  const maxW = Math.max(400, wrap.clientWidth - 4);
  const maxH = 520;
  if (ndim === 1) {
    const cx = Math.max(MIN_CELL, Math.floor(maxW / Nx));
    const cy = Math.max(cx, 60);
    return [cx, cy];
  }
  const cs = Math.max(MIN_CELL, Math.floor(Math.min(maxW / Nx, maxH / Ny)));
  return [cs, cs];
}
let [CELL_X, CELL_Y] = computeCellSize();
canvas.width = Nx * CELL_X;
canvas.height = Ny * CELL_Y;

function hexToRgba(hex, a = 255) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, a];
}
const rgbaPalette = ncColours.map(c => hexToRgba(c, 255));

// Visible-node layout within each cell slot. Shared by drawGeometry and
// the hover/selected overlays so their wire outlines hug the coloured
// square exactly. Recomputed alongside CELL_X/CELL_Y on resize.
let nodeW = 0, nodeH = 0, nodeOffX = 0, nodeOffY = 0;
function computeNodeLayout() {
  // Margin is ~12.5% of the cell on each side, min 1 px so dense grids
  // (CELL=MIN_CELL) still get a visible gap between nodes.
  const marginX = Math.max(1, Math.floor(CELL_X * 0.125));
  const marginY = Math.max(1, Math.floor(CELL_Y * 0.125));
  nodeW = CELL_X - 2 * marginX;
  nodeH = CELL_Y - 2 * marginY;
  // 1D cell slots are intentionally tall (so they stay clickable) but
  // the drawn node itself should be a square, centred in the slot.
  if (ndim === 1) {
    const s = Math.max(1, Math.min(nodeW, nodeH));
    nodeW = s;
    nodeH = s;
  }
  nodeOffX = Math.floor((CELL_X - nodeW) / 2);
  nodeOffY = Math.floor((CELL_Y - nodeH) / 2);
}
computeNodeLayout();

function drawGeometry() {
  const w = canvas.width, h = canvas.height;
  // Image data is zero-initialised → gap pixels stay alpha=0 (transparent),
  // exposing the VSCode editor background between nodes. Matches the 3D
  // "node is a small cube in the middle of its cell" look.
  const img = ctx.createImageData(w, h);
  const data = img.data;
  for (let cellX = 0; cellX < Nx; cellX++) {
    for (let cellY = 0; cellY < Ny; cellY++) {
      const id = ncAt(cellX, cellY);
      const rgba = rgbaPalette[Math.max(0, id - 1)] || [0, 0, 0, 255];
      const px0 = cellX * CELL_X + nodeOffX;
      // Flip y so cell (0,0) is at bottom-left (matches GeLB convention).
      const py0 = h - (cellY + 1) * CELL_Y + nodeOffY;
      for (let dy = 0; dy < nodeH; dy++) {
        for (let dx = 0; dx < nodeW; dx++) {
          const idx = ((py0 + dy) * w + (px0 + dx)) * 4;
          data[idx]     = rgba[0];
          data[idx + 1] = rgba[1];
          data[idx + 2] = rgba[2];
          data[idx + 3] = rgba[3];
        }
      }
    }
  }
  ctx.putImageData(img, 0, 0);
}
drawGeometry();

// ===== Pan & zoom =====
// CSS transform on #canvasInner — the hover/selected overlays sit inside
// the same wrapper, so they ride along automatically.
const inner = document.getElementById('canvasInner');
const wrap = document.getElementById('canvasWrap');
const zoomLabel = document.getElementById('zoomLabel');
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 40;
let zoom = 1;
let panX = 0;
let panY = 0;
let panning = false;
let panStart = null;
let suppressNextClick = false;

function applyTransform() {
  inner.style.transform =
    'translate(' + panX + 'px, ' + panY + 'px) scale(' + zoom + ')';
  if (zoomLabel) zoomLabel.textContent = Math.round(zoom * 100) + '%';
}

function resetView() {
  zoom = 1; panX = 0; panY = 0;
  applyTransform();
}

function zoomAt(wrapX, wrapY, factor) {
  const newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom * factor));
  if (newZoom === zoom) return;
  // Inner-space point under cursor stays put:
  //   p = (wrapX - panX) / zoom  →  panX' = wrapX - p*newZoom
  const px = (wrapX - panX) / zoom;
  const py = (wrapY - panY) / zoom;
  zoom = newZoom;
  panX = wrapX - px * newZoom;
  panY = wrapY - py * newZoom;
  applyTransform();
}

function zoomAtCenter(factor) {
  const r = wrap.getBoundingClientRect();
  zoomAt(r.width / 2, r.height / 2, factor);
}

// Smoothly pan so that the given cell ends up under the wrap's centre.
// Δpan = wrap-centre − current cell-centre in wrap-relative coords.
// canvas.getBoundingClientRect() already reflects the flex-centering AND
// the current transform, so it gives us exactly where the cell sits now.
let smoothTimer = null;
function centerOnCell(cellX, cellY) {
  const wrapRect = wrap.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();
  const [pxL, pxT] = pxOfCell(cellX, cellY);
  const cellCxNow = (canvasRect.left - wrapRect.left)
                    + (pxL + CELL_X / 2) * zoom;
  const cellCyNow = (canvasRect.top - wrapRect.top)
                    + (pxT + CELL_Y / 2) * zoom;
  panX += wrapRect.width / 2 - cellCxNow;
  panY += wrapRect.height / 2 - cellCyNow;
  inner.classList.add('smooth');
  applyTransform();
  if (smoothTimer) clearTimeout(smoothTimer);
  smoothTimer = setTimeout(() => {
    inner.classList.remove('smooth');
    smoothTimer = null;
  }, 280);
}

applyTransform();

wrap.addEventListener('wheel', (e) => {
  e.preventDefault();
  const r = wrap.getBoundingClientRect();
  // Smooth factor: works for both trackpad (small deltaY) and mouse wheel.
  const factor = Math.pow(1.0015, -e.deltaY);
  zoomAt(e.clientX - r.left, e.clientY - r.top, factor);
}, { passive: false });

wrap.addEventListener('mousedown', (e) => {
  const usePan = e.button === 1 || (e.button === 0 && e.altKey);
  if (!usePan) return;
  e.preventDefault();
  panning = true;
  panStart = { x: e.clientX - panX, y: e.clientY - panY };
  wrap.style.cursor = 'grabbing';
  hoverEl.style.display = 'none';
});

window.addEventListener('mousemove', (e) => {
  if (!panning) return;
  panX = e.clientX - panStart.x;
  panY = e.clientY - panStart.y;
  applyTransform();
});

window.addEventListener('mouseup', (e) => {
  if (!panning) return;
  panning = false;
  wrap.style.cursor = '';
  // If the drag moved the pointer, swallow the trailing click so we don't
  // accidentally lock-select a cell.
  if (e.button === 0 && e.altKey) suppressNextClick = true;
});

document.getElementById('btnFit').addEventListener('click', resetView);
document.getElementById('btnZoomIn').addEventListener(
  'click', () => zoomAtCenter(1.25));
document.getElementById('btnZoomOut').addEventListener(
  'click', () => zoomAtCenter(1 / 1.25));

// Keyboard shortcuts: 0 = reset, +/- = zoom, arrow keys = pan, space = stencil.
window.addEventListener('keydown', (e) => {
  if (e.target && /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  if (e.key === '0') { resetView(); e.preventDefault(); }
  else if (e.key === '+' || e.key === '=') { zoomAtCenter(1.25); e.preventDefault(); }
  else if (e.key === '-' || e.key === '_') { zoomAtCenter(1 / 1.25); e.preventDefault(); }
  else if (e.key === 'ArrowLeft')  { panX += 40; applyTransform(); e.preventDefault(); }
  else if (e.key === 'ArrowRight') { panX -= 40; applyTransform(); e.preventDefault(); }
  else if (e.key === 'ArrowUp')    { panY += 40; applyTransform(); e.preventDefault(); }
  else if (e.key === 'ArrowDown')  { panY -= 40; applyTransform(); e.preventDefault(); }
  else if (e.key === ' ')          { startStencilAnim(); e.preventDefault(); }
});

// ===== Stencil animation =====
// On Space with a cell selected: fade in blue squares over every cell we
// read any DF from, fade them out, then fade in red squares over every
// cell we write to, fade them out. Total duration = STENCIL_ANIM_MS,
// split into four equal phases. Read/write target cells are derived from
// the currently-selected block's spatial_offsets, relative to the
// selected cell (target = selectedCell + offset). Self-read and
// self-write targets are included — they simply highlight the selected
// cell itself.
const STENCIL_READ_COLOR = '#2979ff';
const STENCIL_WRITE_COLOR = '#e53935';
const STENCIL_PEAK_ALPHA = 0.55;
let stencilAnim = null;  // { start, readDivs, writeDivs, raf }

function stencilTargetsFor(accesses, cx, cy) {
  const out = [];
  const seen = new Set();
  for (const a of accesses) {
    const o = a.spatial_offsets;
    if (!o) continue;
    const dx = o[0] | 0;
    const dy = (ndim >= 2 ? (o[1] | 0) : 0);
    const tx = cx + dx, ty = cy + dy;
    if (tx < 0 || tx >= Nx || ty < 0 || ty >= Ny) continue;
    const key = tx + ',' + ty;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([tx, ty]);
  }
  return out;
}

function makeStencilOverlays(targets, color) {
  const divs = [];
  for (const [tx, ty] of targets) {
    const d = document.createElement('div');
    d.className = 'stencilTarget';
    const [px, py] = pxOfCell(tx, ty);
    d.style.left = (px + nodeOffX) + 'px';
    d.style.top = (py + nodeOffY) + 'px';
    d.style.width = nodeW + 'px';
    d.style.height = nodeH + 'px';
    d.style.background = color;
    inner.appendChild(d);
    divs.push(d);
  }
  return divs;
}

function cancelStencilAnim() {
  if (!stencilAnim) return;
  if (stencilAnim.raf) cancelAnimationFrame(stencilAnim.raf);
  for (const d of stencilAnim.readDivs) d.remove();
  for (const d of stencilAnim.writeDivs) d.remove();
  stencilAnim = null;
}

function startStencilAnim() {
  if (!selectedCell || !blockSelect.value) return;
  const block = sten.blocks[blockSelect.value];
  if (!block) return;
  cancelStencilAnim();
  const [cx, cy] = selectedCell;
  const readTargets = stencilTargetsFor(block.reads, cx, cy);
  const writeTargets = stencilTargetsFor(block.writes, cx, cy);
  stencilAnim = {
    start: performance.now(),
    readDivs: makeStencilOverlays(readTargets, STENCIL_READ_COLOR),
    writeDivs: makeStencilOverlays(writeTargets, STENCIL_WRITE_COLOR),
    raf: 0,
  };
  const tick = (now) => {
    if (!stencilAnim) return;
    const elapsed = now - stencilAnim.start;
    const phase = STENCIL_ANIM_MS / 4;
    let readA = 0, writeA = 0;
    if (elapsed < phase)              readA = elapsed / phase;
    else if (elapsed < 2 * phase)     readA = 1 - (elapsed - phase) / phase;
    else if (elapsed < 3 * phase)     writeA = (elapsed - 2 * phase) / phase;
    else if (elapsed < 4 * phase)     writeA = 1 - (elapsed - 3 * phase) / phase;
    else { cancelStencilAnim(); return; }
    const rs = (readA * STENCIL_PEAK_ALPHA).toFixed(3);
    const ws = (writeA * STENCIL_PEAK_ALPHA).toFixed(3);
    for (const d of stencilAnim.readDivs)  d.style.opacity = rs;
    for (const d of stencilAnim.writeDivs) d.style.opacity = ws;
    stencilAnim.raf = requestAnimationFrame(tick);
  };
  stencilAnim.raf = requestAnimationFrame(tick);
}

// ===== Cell-coord helpers =====
function cellAtPx(px, py) {
  const cellX = Math.floor(px / CELL_X);
  // Flip y back: canvas y=0 is top, cell y=0 is bottom
  const cellY = Ny - 1 - Math.floor(py / CELL_Y);
  if (cellX < 0 || cellX >= Nx || cellY < 0 || cellY >= Ny) return null;
  return [cellX, cellY];
}

function pxOfCell(cellX, cellY) {
  return [cellX * CELL_X, canvas.height - (cellY + 1) * CELL_Y];
}

// ===== Hover indicator =====
const hoverEl = document.getElementById('cellHover');
const selectedEl = document.getElementById('cellSelected');
const status = document.getElementById('status');

function showHoverAt(cellX, cellY) {
  const [px, py] = pxOfCell(cellX, cellY);
  hoverEl.style.left = (px + nodeOffX) + 'px';
  hoverEl.style.top = (py + nodeOffY) + 'px';
  hoverEl.style.width = nodeW + 'px';
  hoverEl.style.height = nodeH + 'px';
  hoverEl.style.display = 'block';
  const id = ncAt(cellX, cellY);
  const name = geo.nc_order[id - 1] || '?';
  status.textContent =
    \`(\${cellX}, \${cellY}) → \${name} (id=\${id})\`;
}

// Event → canvas-internal pixel (works under any transform on #canvasInner).
function localFromEvent(e) {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return [-1, -1];
  return [
    (e.clientX - rect.left) * canvas.width / rect.width,
    (e.clientY - rect.top) * canvas.height / rect.height,
  ];
}

const HOVER_HELP =
  'Hover to inspect · Click to select · Space = stencil animation' +
  ' · Wheel = zoom · Alt-drag = pan.';

canvas.addEventListener('mousemove', (e) => {
  if (panning) return;
  const [px, py] = localFromEvent(e);
  const cell = cellAtPx(px, py);
  if (cell) showHoverAt(cell[0], cell[1]);
});

canvas.addEventListener('mouseleave', () => {
  hoverEl.style.display = 'none';
  status.textContent = HOVER_HELP;
});

// ===== Click → select + show stencil =====
let selectedCell = null;

canvas.addEventListener('click', (e) => {
  if (suppressNextClick) { suppressNextClick = false; return; }
  const [px, py] = localFromEvent(e);
  const cell = cellAtPx(px, py);
  if (!cell) return;
  selectCell(cell[0], cell[1]);
});

function selectCell(cellX, cellY, opts) {
  selectedCell = [cellX, cellY];
  const [pxL, pxT] = pxOfCell(cellX, cellY);
  selectedEl.style.left = (pxL + nodeOffX) + 'px';
  selectedEl.style.top = (pxT + nodeOffY) + 'px';
  selectedEl.style.width = nodeW + 'px';
  selectedEl.style.height = nodeH + 'px';
  selectedEl.style.display = 'block';
  populateBlockOptions(cellX, cellY);
  drawStencilForSelectedBlock();
  if (!opts || opts.center !== false) centerOnCell(cellX, cellY);
}

// ===== Per-NC block dropdown =====
const blockSelect = document.getElementById('blockSelect');
function populateBlockOptions(cellX, cellY) {
  const id = ncAt(cellX, cellY);
  const name = geo.nc_order[id - 1];
  if (!name) return;
  const info = geo.nc_info[name];
  blockSelect.innerHTML = '';
  for (const role of ['initializer', 'dynamic', 'gauge']) {
    const blkName = info[role];
    if (blkName && sten.blocks[blkName]) {
      const opt = document.createElement('option');
      opt.value = blkName;
      opt.textContent = \`\${role}: \${blkName}\`;
      // default to dynamic if available
      if (role === 'dynamic') opt.selected = true;
      blockSelect.appendChild(opt);
    }
  }
}
blockSelect.addEventListener('change', drawStencilForSelectedBlock);

// ===== Render stencil description (textual, side panel only) =====
function drawStencilForSelectedBlock() {
  const stenDiv = document.getElementById('stencils');
  stenDiv.innerHTML = '';
  if (!selectedCell || !blockSelect.value) {
    document.getElementById('title').textContent = '';
    document.getElementById('info').innerHTML = '';
    return;
  }
  const [cx, cy] = selectedCell;
  const id = ncAt(cx, cy);
  const ncName = geo.nc_order[id - 1] || '?';
  const info = geo.nc_info[ncName];

  document.getElementById('title').textContent =
    \`Cell (\${cx}, \${cy}) ∈ '\${ncName}'\`;

  const infoDiv = document.getElementById('info');
  const masked = info.masked ? ' (masked)' : '';
  const isStatic = !info.dynamic ? ' (static)' : '';
  infoDiv.innerHTML = \`
    <table>
      <tr><td class="k">NC ID</td><td>\${info.nc_id}\${masked}\${isStatic}</td></tr>
      <tr><td class="k">init</td><td>\${info.initializer || '—'}</td></tr>
      <tr><td class="k">dynamic</td><td>\${info.dynamic || '—'}</td></tr>
      <tr><td class="k">gauge</td><td>\${info.gauge || '—'}</td></tr>
    </table>
  \`;

  const block = sten.blocks[blockSelect.value];
  if (!block) return;

  const reads = block.reads;
  const writes = block.writes;

  // Match the GeLB source notation: f.in[<offsets> | <df>] for reads,
  // f.out[<offsets> | <df>] for writes; <df> is the integer DF index
  // or ':' when the access covers all DFs of the lattice.
  function fmtAccess(a, direction) {
    const offs = a.spatial_offsets.join(', ');
    const df = a.df_index === null ? ':' : a.df_index;
    return \`\${a.lattice_name}.\${direction}[\${offs} | \${df}]\`;
  }

  const readsTbl = document.createElement('table');
  readsTbl.className = 'reads';
  readsTbl.innerHTML = '<tr><td class="k"><b>Reads (' +
    reads.length + ')</b></td></tr>';
  for (const a of reads) {
    const tr = document.createElement('tr');
    tr.innerHTML = \`<td><code>\${fmtAccess(a, 'in')}</code></td>\`;
    readsTbl.appendChild(tr);
  }
  stenDiv.appendChild(readsTbl);

  const writesTbl = document.createElement('table');
  writesTbl.className = 'writes';
  writesTbl.innerHTML = '<tr><td class="k"><b>Writes (' +
    writes.length + ')</b></td></tr>';
  for (const a of writes) {
    const tr = document.createElement('tr');
    tr.innerHTML = \`<td><code>\${fmtAccess(a, 'out')}</code></td>\`;
    writesTbl.appendChild(tr);
  }
  stenDiv.appendChild(writesTbl);
}

// ===== Legend =====
const legendDiv = document.getElementById('legend');
for (let i = 0; i < geo.nc_order.length; i++) {
  const name = geo.nc_order[i];
  const info = geo.nc_info[name];
  const cnt = ncCounts.get(name) || 0;
  const pct = (100 * cnt / total).toFixed(1);
  const tags = [];
  if (info.masked) tags.push('masked');
  if (!info.dynamic) tags.push('static');
  const tagStr = tags.length ? ' (' + tags.join(', ') + ')' : '';
  const row = document.createElement('div');
  row.className = 'legend-row';
  row.innerHTML = \`<span class="nc-swatch" style="background: \${ncColours[i]}"></span>\` +
    \`<b>\${name}</b>\${tagStr} — \${cnt} (\${pct}%)\`;
  legendDiv.appendChild(row);
}

// ===== Static axis gizmo (lower-left) =====
// 1D: just x. 2D: x + y (y up, matching GeLB convention: y=0 at bottom).
// Sits at #canvasWrap's lower-left, outside #canvasInner, so it does NOT
// inherit the pan/zoom transform and stays anchored to the viewport.
(function buildAxisGizmo() {
  const host = document.getElementById('axisGizmo');
  if (!host) return;
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 72 72');

  const AX_COLOR = '#e54b4b';
  const AY_COLOR = '#5bc75b';

  // Arrowhead markers — one per colour.
  const defs = document.createElementNS(SVG_NS, 'defs');
  function addMarker(id, colour) {
    const marker = document.createElementNS(SVG_NS, 'marker');
    marker.setAttribute('id', id);
    marker.setAttribute('markerWidth', '7');
    marker.setAttribute('markerHeight', '7');
    marker.setAttribute('refX', '6');
    marker.setAttribute('refY', '3.5');
    marker.setAttribute('orient', 'auto');
    marker.setAttribute('viewBox', '0 0 7 7');
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M0,0 L7,3.5 L0,7 Z');
    path.setAttribute('fill', colour);
    marker.appendChild(path);
    defs.appendChild(marker);
  }
  addMarker('gelb-arrow-x', AX_COLOR);
  addMarker('gelb-arrow-y', AY_COLOR);
  svg.appendChild(defs);

  function addArrow(x1, y1, x2, y2, colour, markerId) {
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', x1); line.setAttribute('y1', y1);
    line.setAttribute('x2', x2); line.setAttribute('y2', y2);
    line.setAttribute('stroke', colour);
    line.setAttribute('stroke-width', '2.5');
    line.setAttribute('stroke-linecap', 'round');
    line.setAttribute('marker-end', 'url(#' + markerId + ')');
    svg.appendChild(line);
  }
  function addLabel(x, y, colour, text) {
    const t = document.createElementNS(SVG_NS, 'text');
    t.setAttribute('x', x); t.setAttribute('y', y);
    t.setAttribute('fill', colour);
    t.setAttribute('font-family', 'sans-serif');
    t.setAttribute('font-size', '14');
    t.setAttribute('font-weight', 'bold');
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('dominant-baseline', 'middle');
    t.setAttribute('stroke', 'rgba(0,0,0,0.75)');
    t.setAttribute('stroke-width', '3');
    t.setAttribute('paint-order', 'stroke');
    t.textContent = text;
    svg.appendChild(t);
  }

  // x arrow (both 1D and 2D)
  addArrow(12, 58, 54, 58, AX_COLOR, 'gelb-arrow-x');
  addLabel(64, 58, AX_COLOR, 'x');
  if (ndim >= 2) {
    addArrow(12, 58, 12, 16, AY_COLOR, 'gelb-arrow-y');
    addLabel(12, 8, AY_COLOR, 'y');
  }
  host.appendChild(svg);
})();

// ===== Resize handling =====
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    const [ncx, ncy] = computeCellSize();
    if (ncx !== CELL_X || ncy !== CELL_Y) {
      CELL_X = ncx;
      CELL_Y = ncy;
      canvas.width = Nx * CELL_X;
      canvas.height = Ny * CELL_Y;
      computeNodeLayout();
      drawGeometry();
      cancelStencilAnim();  // overlay positions would be stale otherwise
      if (selectedCell) selectCell(selectedCell[0], selectedCell[1],
                                   { center: false });
    }
  }, 100);
});
</script>
</body>
</html>`;
    }

    _renderHtml3D(
        jsonStr: string,
        threeUri: string,
        controlsUri: string,
        cspSource: string,
        stencilAnimMs: number,
    ): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src ${cspSource} 'unsafe-inline'; style-src ${cspSource} 'unsafe-inline'; img-src ${cspSource} data:; connect-src 'none';">
<style>
  body { font-family: var(--vscode-font-family); margin: 0; padding: 8px;
         color: var(--vscode-foreground);
         background: var(--vscode-editor-background); overflow: hidden; }
  #wrap { display: grid; grid-template-columns: 1fr 280px; gap: 12px;
          height: calc(100vh - 64px); }
  #canvasWrap { position: relative; border: 1px solid var(--vscode-panel-border);
                background: var(--vscode-editor-background);
                min-height: 320px; overflow: hidden; touch-action: none; }
  #mainCanvas { display: block; outline: none; }
  #side { font-size: 11px; overflow-y: auto; }
  #side h3 { font-size: 12px; margin: 0 0 6px 0; }
  #side h4 { font-size: 11px; margin: 8px 0 4px 0;
             border-bottom: 1px solid var(--vscode-panel-border); }
  .nc-swatch { display: inline-block; width: 10px; height: 10px;
               vertical-align: middle; margin-right: 4px;
               border: 1px solid #555; }
  .legend-row { padding: 1px 0; }
  table { border-collapse: collapse; font-size: 10px; }
  td { padding: 1px 6px 1px 0; vertical-align: top; }
  td.k { color: var(--vscode-descriptionForeground); }
  /* Reads/writes text colour matches the stencil-animation overlay colour
     one-to-one, so the side-panel table reads as the same information
     the on-screen fade-in is showing. */
  .reads td { color: #2979ff; }
  .writes td { color: #e53935; }
  #status { font-family: monospace; font-size: 10px;
            color: var(--vscode-descriptionForeground);
            min-height: 14px; padding: 2px 0; }
  #viewToolbar { display: flex; align-items: center; gap: 4px;
                 padding: 2px 0 4px 0; font-size: 11px;
                 color: var(--vscode-descriptionForeground); }
  #viewToolbar button { font-size: 11px; padding: 1px 8px;
                background: var(--vscode-button-secondaryBackground, transparent);
                color: var(--vscode-button-secondaryForeground, inherit);
                border: 1px solid var(--vscode-panel-border);
                cursor: pointer; }
  #viewToolbar button:hover {
                background: var(--vscode-button-secondaryHoverBackground,
                                    var(--vscode-list-hoverBackground)); }
  #zoomLabel { font-family: monospace; min-width: 48px; text-align: right; }
  #blockSelect { width: 100%; font-size: 11px; padding: 2px;
                 background: var(--vscode-input-background);
                 color: var(--vscode-input-foreground);
                 border: 1px solid var(--vscode-input-border); }
</style>
</head>
<body>
<div id="status">Drag = rotate  ·  Wheel = zoom  ·  WASD = fly  ·  Q/E = up/down  ·  Shift = faster  ·  R or 0 = reset  ·  Click = select  ·  Space = stencil</div>
<div id="viewToolbar">
  <button id="btnFit" title="Reset view (R or 0)">Fit</button>
  <button id="btnZoomOut" title="Zoom out (-)">−</button>
  <button id="btnZoomIn" title="Zoom in (+)">+</button>
  <button id="btnInterior" title="Toggle all cells (translucent) / shell only">Interior: all</button>
  <span id="zoomLabel">100%</span>
</div>
<div id="wrap">
  <div id="canvasWrap"><canvas id="mainCanvas" tabindex="0"></canvas></div>
  <div id="side">
    <h3 id="title"></h3>
    <div id="info"></div>
    <h4>Legend</h4>
    <div id="legend"></div>
    <h4>Blocks (click cell first)</h4>
    <select id="blockSelect"></select>
    <div id="stencils"></div>
  </div>
</div>

<script type="importmap">
{ "imports": { "three": "${threeUri}" } }
</script>
<script type="module">
'use strict';
console.log('GeLB interactive view 3D: build 2026-04-19h (source-like DF notation)');
// Total stencil-animation duration (ms). Configured via the
// "gelb.stencilAnimationDurationMs" setting; embedded here by the host.
const STENCIL_ANIM_MS = ${stencilAnimMs};

import * as THREE from 'three';
import { OrbitControls } from '${controlsUri}';

// ===== Embedded data =====
const DATA = ${jsonStr};

// ===== Decode nc_map → Int32Array =====
function decodeNcMap(g) {
  const bin = atob(g.nc_map_b64);
  const buf = new ArrayBuffer(bin.length);
  const u8 = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new Int32Array(buf);
}
const geo = DATA.geometry;
const sten = DATA.stencils;
const nc_map = decodeNcMap(geo);
const Nx = geo.nc_map_shape[0];
const Ny = geo.nc_map_shape[1];
const Nz = geo.nc_map_shape[2];
function ncAt(x, y, z) {
  if (x < 0 || x >= Nx || y < 0 || y >= Ny || z < 0 || z >= Nz) return -1;
  return nc_map[(x * Ny + y) * Nz + z];
}

// ===== Colour palette (matches 1D / 2D) =====
const PALETTE = [
  '#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3',
  '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3',
  '#1b9e77', '#d95f02'
];
const ncColours = geo.nc_order.map((_, i) => PALETTE[i % PALETTE.length]);

// ===== Cell counts for legend =====
const ncCounts = new Map();
for (const name of geo.nc_order) ncCounts.set(name, 0);
for (let i = 0; i < nc_map.length; i++) {
  const id = nc_map[i];
  if (id >= 1 && id <= geo.nc_order.length) {
    const name = geo.nc_order[id - 1];
    ncCounts.set(name, (ncCounts.get(name) || 0) + 1);
  }
}
const total = nc_map.length;

// ===== Scene & camera =====
const canvas = document.getElementById('mainCanvas');
const wrap = document.getElementById('canvasWrap');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);

const scene = new THREE.Scene();
const bgCss = getComputedStyle(document.body)
  .getPropertyValue('--vscode-editor-background').trim();
scene.background = new THREE.Color(bgCss || '#1e1e1e');

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(Nx * 2, Ny * 3, Nz * 2);
scene.add(keyLight);
const fillLight = new THREE.DirectionalLight(0xffffff, 0.25);
fillLight.position.set(-Nx, -Ny, -Nz);
scene.add(fillLight);

const domainCenter = new THREE.Vector3(Nx / 2, Ny / 2, Nz / 2);
const domainDiag = Math.sqrt(Nx * Nx + Ny * Ny + Nz * Nz);
const initialDist = Math.max(domainDiag * 1.4, 5);

const camera = new THREE.PerspectiveCamera(
  45, 1, 0.05, Math.max(Nx, Ny, Nz) * 50 + 100);

// zoomLabel is used by updateZoomLabel(), which resetView() calls
// during scene setup — declare it eagerly so we don't trip the TDZ.
const zoomLabel = document.getElementById('zoomLabel');
function updateZoomLabel() {
  const d = camera.position.distanceTo(controls.target);
  if (d > 0) {
    zoomLabel.textContent = Math.round(initialDist / d * 100) + '%';
  }
}

function resetView() {
  camera.position.set(
    domainCenter.x + initialDist * 0.65,
    domainCenter.y + initialDist * 0.55,
    domainCenter.z + initialDist * 0.80,
  );
  controls.target.copy(domainCenter);
  controls.update();
  updateZoomLabel();
}

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.12;
controls.screenSpacePanning = true;
controls.target.copy(domainCenter);
resetView();

function sizeCanvas() {
  const rect = wrap.getBoundingClientRect();
  const w = Math.max(320, Math.floor(rect.width));
  const h = Math.max(240, Math.floor(rect.height));
  renderer.setSize(w, h, true);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
sizeCanvas();

// ===== Axis gizmo (lower-left orientation indicator) =====
// Second scene + camera rendered in a scissored viewport; the gizmo camera
// orbits the origin to mirror the main camera's direction, so the X / Y / Z
// arrows rotate in sync with the lattice view.
const AXIS_VIEWPORT_PX = 96;
const AXIS_MARGIN_PX = 6;
const axisScene = new THREE.Scene();
const axisCamera = new THREE.PerspectiveCamera(50, 1, 0.1, 10);
axisCamera.up.set(0, 1, 0);

const AXIS_X_COLOR = 0xe54b4b;
const AXIS_Y_COLOR = 0x5bc75b;
const AXIS_Z_COLOR = 0x4d92ff;
function axisLabel(text, hex) {
  const c = document.createElement('canvas');
  c.width = 64; c.height = 64;
  const g = c.getContext('2d');
  g.clearRect(0, 0, 64, 64);
  g.font = 'bold 46px sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  // Dark outline so labels stay legible on any background.
  g.lineWidth = 6; g.strokeStyle = 'rgba(0, 0, 0, 0.75)';
  g.strokeText(text, 32, 32);
  g.fillStyle = '#' + hex.toString(16).padStart(6, '0');
  g.fillText(text, 32, 32);
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial(
    { map: tex, transparent: true, depthTest: false });
  const sp = new THREE.Sprite(mat);
  sp.scale.set(0.42, 0.42, 0.42);
  return sp;
}
const AXIS_LEN = 0.95;
const AXIS_HEAD_LEN = 0.22;
const AXIS_HEAD_WIDTH = 0.14;
const axisSpecs = [
  { dir: new THREE.Vector3(1, 0, 0), color: AXIS_X_COLOR, label: 'x' },
  { dir: new THREE.Vector3(0, 1, 0), color: AXIS_Y_COLOR, label: 'y' },
  { dir: new THREE.Vector3(0, 0, 1), color: AXIS_Z_COLOR, label: 'z' },
];
const origin = new THREE.Vector3(0, 0, 0);
for (const a of axisSpecs) {
  const arrow = new THREE.ArrowHelper(
    a.dir, origin, AXIS_LEN, a.color, AXIS_HEAD_LEN, AXIS_HEAD_WIDTH);
  axisScene.add(arrow);
  const lbl = axisLabel(a.label, a.color);
  lbl.position.copy(a.dir).multiplyScalar(AXIS_LEN + 0.28);
  axisScene.add(lbl);
}
const axisViewDir = new THREE.Vector3();
function renderAxisGizmo() {
  const size = renderer.getSize(new THREE.Vector2());
  if (size.y < AXIS_VIEWPORT_PX + AXIS_MARGIN_PX) return;  // no room
  axisViewDir.subVectors(camera.position, controls.target);
  if (axisViewDir.lengthSq() === 0) axisViewDir.set(1, 1, 1);
  axisViewDir.normalize().multiplyScalar(3);
  axisCamera.position.copy(axisViewDir);
  axisCamera.up.copy(camera.up);
  axisCamera.lookAt(0, 0, 0);

  renderer.autoClear = false;
  renderer.clearDepth();
  renderer.setScissorTest(true);
  renderer.setViewport(AXIS_MARGIN_PX, AXIS_MARGIN_PX,
                       AXIS_VIEWPORT_PX, AXIS_VIEWPORT_PX);
  renderer.setScissor(AXIS_MARGIN_PX, AXIS_MARGIN_PX,
                      AXIS_VIEWPORT_PX, AXIS_VIEWPORT_PX);
  renderer.render(axisScene, axisCamera);
  renderer.setScissorTest(false);
  renderer.setViewport(0, 0, size.x, size.y);
  renderer.autoClear = true;
}

// ===== Shell computation =====
// A cell is "on the shell" iff (a) it lies on a domain face, or (b) one of
// its 6 face-neighbours has a different nc_id (or is unassigned).
function isShellCell(x, y, z, id) {
  if (x === 0 || x === Nx - 1) return true;
  if (y === 0 || y === Ny - 1) return true;
  if (z === 0 || z === Nz - 1) return true;
  if (ncAt(x - 1, y, z) !== id) return true;
  if (ncAt(x + 1, y, z) !== id) return true;
  if (ncAt(x, y - 1, z) !== id) return true;
  if (ncAt(x, y + 1, z) !== id) return true;
  if (ncAt(x, y, z - 1) !== id) return true;
  if (ncAt(x, y, z + 1) !== id) return true;
  return false;
}

const nNc = geo.nc_order.length;
const cellsShell = Array.from({ length: nNc }, () => []);
const cellsAll = Array.from({ length: nNc }, () => []);
for (let x = 0; x < Nx; x++) {
  for (let y = 0; y < Ny; y++) {
    for (let z = 0; z < Nz; z++) {
      const id = nc_map[(x * Ny + y) * Nz + z];
      if (id < 1 || id > nNc) continue;
      const flat = (x * Ny + y) * Nz + z;
      cellsAll[id - 1].push(flat);
      if (isShellCell(x, y, z, id)) cellsShell[id - 1].push(flat);
    }
  }
}
function flatToXyz(flat) {
  const z = flat % Nz;
  const yx = (flat - z) / Nz;
  const y = yx % Ny;
  const x = (yx - y) / Ny;
  return [x, y, z];
}

// ===== InstancedMesh per NC =====
// Nodes are drawn as small opaque cubes (CELL_CUBE_SIZE of the unit cell),
// so gaps between adjacent cells let the user see interior nodes behind
// the front faces.
const CELL_CUBE_SIZE = 0.5;
const boxGeom = new THREE.BoxGeometry(
  CELL_CUBE_SIZE, CELL_CUBE_SIZE, CELL_CUBE_SIZE);
const meshes = [];
for (let i = 0; i < nNc; i++) {
  const mat = new THREE.MeshLambertMaterial({ color: ncColours[i] });
  const mesh = new THREE.InstancedMesh(boxGeom, mat, cellsAll[i].length || 1);
  mesh.userData.ncIndex = i;
  mesh.frustumCulled = false;
  scene.add(mesh);
  meshes.push(mesh);
}
const dummy = new THREE.Object3D();

// Interior toggle: 0 = all cells (default — gaps between small cubes keep
// interior nodes visible), 1 = shell only.
let interiorMode = 0;
function cellsForMode(ncIdx) {
  return interiorMode === 0 ? cellsAll[ncIdx] : cellsShell[ncIdx];
}

function populateInstances() {
  for (let i = 0; i < nNc; i++) {
    const mesh = meshes[i];
    const cells = cellsForMode(i);
    for (let k = 0; k < cells.length; k++) {
      const [x, y, z] = flatToXyz(cells[k]);
      dummy.position.set(x + 0.5, y + 0.5, z + 0.5);
      dummy.updateMatrix();
      mesh.setMatrixAt(k, dummy.matrix);
    }
    mesh.count = cells.length;
    mesh.instanceMatrix.needsUpdate = true;
  }
}
populateInstances();

// ===== Selection =====
const raycaster = new THREE.Raycaster();
const mouseNdc = new THREE.Vector2();
let selectedCell = null;
let selectionHelper = null;
let hoveredCell = null;
let hoverHelper = null;

// Selection reads as a strong, saturated yellow; hover as a soft warm
// amber. Hover wireframe is slightly smaller so that, when the cursor
// sits on the already-selected cell, the two boxes don't z-fight — the
// selected one cleanly surrounds the hover one.
const HOVER_COLOR = 0xffc266;
const SELECT_COLOR = 0xffdd00;

function buildWireHelper(x, y, z, size, color) {
  const geom = new THREE.EdgesGeometry(new THREE.BoxGeometry(size, size, size));
  const mat = new THREE.LineBasicMaterial({ color });
  const helper = new THREE.LineSegments(geom, mat);
  helper.position.set(x + 0.5, y + 0.5, z + 0.5);
  return helper;
}
function disposeHelper(h) {
  if (!h) return null;
  scene.remove(h);
  h.geometry.dispose();
  h.material.dispose();
  return null;
}

function updateSelectionHelper() {
  selectionHelper = disposeHelper(selectionHelper);
  if (!selectedCell) return;
  const [x, y, z] = selectedCell;
  selectionHelper = buildWireHelper(
    x, y, z, CELL_CUBE_SIZE + 0.12, SELECT_COLOR);
  scene.add(selectionHelper);
}

function updateHoverHelper() {
  hoverHelper = disposeHelper(hoverHelper);
  if (!hoveredCell) return;
  const [x, y, z] = hoveredCell;
  // Skip drawing hover when it coincides with the selection — the
  // selected wire already covers it.
  if (selectedCell &&
      selectedCell[0] === x && selectedCell[1] === y && selectedCell[2] === z) {
    return;
  }
  hoverHelper = buildWireHelper(
    x, y, z, CELL_CUBE_SIZE + 0.06, HOVER_COLOR);
  scene.add(hoverHelper);
}

function selectCellXyz(x, y, z) {
  selectedCell = [x, y, z];
  updateSelectionHelper();
  updateHoverHelper();  // hide/restore hover overlay as appropriate
  populateBlockOptions(x, y, z);
  drawStencilForSelectedBlock();
}

// Pick the frontmost cell under an event's mouse position. Returns
// [x, y, z] or null if the ray misses all meshes. Shared by the click
// and hover code paths.
function pickCellAt(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  mouseNdc.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  mouseNdc.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouseNdc, camera);
  const hits = raycaster.intersectObjects(meshes, false);
  if (hits.length === 0) return null;
  const hit = hits[0];
  const ncIdx = hit.object.userData.ncIndex;
  const k = hit.instanceId;
  const cells = cellsForMode(ncIdx);
  if (k == null || k < 0 || k >= cells.length) return null;
  return flatToXyz(cells[k]);
}

// Pointer-drag tracking so a drag-release doesn't count as a selection.
let pointerDownAt = null;
let didDrag = false;
// Latest pointermove awaiting raycast in the next frame; lets us skip
// per-event raycasting on large grids without dropping hover fidelity.
let pendingHoverEvent = null;

canvas.addEventListener('pointerdown', (e) => {
  pointerDownAt = { x: e.clientX, y: e.clientY };
  didDrag = false;
  pendingHoverEvent = null;
  if (hoveredCell) { hoveredCell = null; updateHoverHelper(); }
});
canvas.addEventListener('pointermove', (e) => {
  if (pointerDownAt) {
    const d = Math.hypot(e.clientX - pointerDownAt.x,
                         e.clientY - pointerDownAt.y);
    if (d > 4) didDrag = true;
    return;  // no hover raycasts while dragging the camera
  }
  pendingHoverEvent = e;
});
canvas.addEventListener('pointerup', () => { pointerDownAt = null; });
canvas.addEventListener('pointerleave', () => {
  pointerDownAt = null;
  pendingHoverEvent = null;
  if (hoveredCell) { hoveredCell = null; updateHoverHelper(); }
});

function processPendingHover() {
  if (!pendingHoverEvent) return;
  const e = pendingHoverEvent;
  pendingHoverEvent = null;
  const cell = pickCellAt(e.clientX, e.clientY);
  if (!cell) {
    if (hoveredCell) { hoveredCell = null; updateHoverHelper(); }
    return;
  }
  if (!hoveredCell || hoveredCell[0] !== cell[0]
      || hoveredCell[1] !== cell[1] || hoveredCell[2] !== cell[2]) {
    hoveredCell = cell;
    updateHoverHelper();
  }
}

canvas.addEventListener('click', (e) => {
  if (didDrag) { didDrag = false; return; }
  const cell = pickCellAt(e.clientX, e.clientY);
  if (!cell) return;
  selectCellXyz(cell[0], cell[1], cell[2]);
});

// ===== Block selector & stencil table =====
const blockSelect = document.getElementById('blockSelect');
function populateBlockOptions(x, y, z) {
  const id = ncAt(x, y, z);
  const name = geo.nc_order[id - 1];
  blockSelect.innerHTML = '';
  if (!name) return;
  const info = geo.nc_info[name];
  for (const role of ['initializer', 'dynamic', 'gauge']) {
    const blkName = info[role];
    if (blkName && sten.blocks[blkName]) {
      const opt = document.createElement('option');
      opt.value = blkName;
      opt.textContent = role + ': ' + blkName;
      if (role === 'dynamic') opt.selected = true;
      blockSelect.appendChild(opt);
    }
  }
}
blockSelect.addEventListener('change', drawStencilForSelectedBlock);

function drawStencilForSelectedBlock() {
  const stenDiv = document.getElementById('stencils');
  stenDiv.innerHTML = '';
  if (!selectedCell || !blockSelect.value) {
    document.getElementById('title').textContent = '';
    document.getElementById('info').innerHTML = '';
    return;
  }
  const [cx, cy, cz] = selectedCell;
  const id = ncAt(cx, cy, cz);
  const ncName = geo.nc_order[id - 1] || '?';
  const info = geo.nc_info[ncName];
  document.getElementById('title').textContent =
    \`Cell (\${cx}, \${cy}, \${cz}) ∈ '\${ncName}'\`;
  const infoDiv = document.getElementById('info');
  const masked = info.masked ? ' (masked)' : '';
  const isStatic = !info.dynamic ? ' (static)' : '';
  infoDiv.innerHTML = \`
    <table>
      <tr><td class="k">NC ID</td><td>\${info.nc_id}\${masked}\${isStatic}</td></tr>
      <tr><td class="k">init</td><td>\${info.initializer || '—'}</td></tr>
      <tr><td class="k">dynamic</td><td>\${info.dynamic || '—'}</td></tr>
      <tr><td class="k">gauge</td><td>\${info.gauge || '—'}</td></tr>
    </table>
  \`;
  const block = sten.blocks[blockSelect.value];
  if (!block) return;
  const reads = block.reads;
  const writes = block.writes;
  // Match the GeLB source notation: f.in[<offsets> | <df>] for reads,
  // f.out[<offsets> | <df>] for writes.
  function fmtAccess(a, direction) {
    const offs = a.spatial_offsets.join(', ');
    const df = a.df_index === null ? ':' : a.df_index;
    return \`\${a.lattice_name}.\${direction}[\${offs} | \${df}]\`;
  }
  const readsTbl = document.createElement('table');
  readsTbl.className = 'reads';
  readsTbl.innerHTML = '<tr><td class="k"><b>Reads (' +
    reads.length + ')</b></td></tr>';
  for (const a of reads) {
    const tr = document.createElement('tr');
    tr.innerHTML = \`<td><code>\${fmtAccess(a, 'in')}</code></td>\`;
    readsTbl.appendChild(tr);
  }
  stenDiv.appendChild(readsTbl);
  const writesTbl = document.createElement('table');
  writesTbl.className = 'writes';
  writesTbl.innerHTML = '<tr><td class="k"><b>Writes (' +
    writes.length + ')</b></td></tr>';
  for (const a of writes) {
    const tr = document.createElement('tr');
    tr.innerHTML = \`<td><code>\${fmtAccess(a, 'out')}</code></td>\`;
    writesTbl.appendChild(tr);
  }
  stenDiv.appendChild(writesTbl);
}

// ===== Legend =====
const legendDiv = document.getElementById('legend');
for (let i = 0; i < geo.nc_order.length; i++) {
  const name = geo.nc_order[i];
  const info = geo.nc_info[name];
  const cnt = ncCounts.get(name) || 0;
  const pct = (100 * cnt / total).toFixed(1);
  const tags = [];
  if (info.masked) tags.push('masked');
  if (!info.dynamic) tags.push('static');
  const tagStr = tags.length ? ' (' + tags.join(', ') + ')' : '';
  const row = document.createElement('div');
  row.className = 'legend-row';
  row.innerHTML = \`<span class="nc-swatch" style="background: \${ncColours[i]}"></span>\` +
    \`<b>\${name}</b>\${tagStr} — \${cnt} (\${pct}%)\`;
  legendDiv.appendChild(row);
}

// ===== Toolbar =====
// (zoomLabel + updateZoomLabel are hoisted above, near the camera so that
// resetView() can call them during scene setup without hitting the TDZ.)

function dolly(factor) {
  const offset = new THREE.Vector3()
    .subVectors(camera.position, controls.target);
  offset.multiplyScalar(1 / factor);
  camera.position.copy(controls.target).add(offset);
  controls.update();
  updateZoomLabel();
}

document.getElementById('btnFit').addEventListener('click', resetView);
document.getElementById('btnZoomIn').addEventListener(
  'click', () => dolly(1.25));
document.getElementById('btnZoomOut').addEventListener(
  'click', () => dolly(1 / 1.25));

const btnInterior = document.getElementById('btnInterior');
// Labels indexed by interiorMode: 0 = all cells, 1 = shell only.
const INTERIOR_LABELS = ['Interior: all', 'Interior: shell'];
btnInterior.textContent = INTERIOR_LABELS[interiorMode];
btnInterior.addEventListener('click', () => {
  interiorMode = (interiorMode + 1) % INTERIOR_LABELS.length;
  btnInterior.textContent = INTERIOR_LABELS[interiorMode];
  populateInstances();
});

// ===== Stencil animation =====
// Space on a selected cell: blue fade-in on every cell we read a DF from,
// fade-out, red fade-in on cells we write to, fade-out. Total duration
// = STENCIL_ANIM_MS split into four equal phases. Targets are derived
// from the currently-chosen block's spatial_offsets, relative to the
// selected cell (target = selected + offset). Each target is a small
// semi-transparent cube sharing the node's box geometry; opacity
// updated every animation frame.
const STENCIL_READ_COLOR = 0x2979ff;
const STENCIL_WRITE_COLOR = 0xe53935;
const STENCIL_PEAK_ALPHA = 0.55;
const stencilMeshes = [];  // {mesh, phase: 'read'|'write'}
let stencilAnimStart = null;

function stencilTargetsFor3D(accesses, cx, cy, cz) {
  const out = [];
  const seen = new Set();
  for (const a of accesses) {
    const o = a.spatial_offsets;
    if (!o) continue;
    const dx = o[0] | 0;
    const dy = o.length > 1 ? (o[1] | 0) : 0;
    const dz = o.length > 2 ? (o[2] | 0) : 0;
    const tx = cx + dx, ty = cy + dy, tz = cz + dz;
    if (tx < 0 || tx >= Nx || ty < 0 || ty >= Ny || tz < 0 || tz >= Nz) continue;
    const key = tx + ',' + ty + ',' + tz;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([tx, ty, tz]);
  }
  return out;
}

function clearStencilMeshes() {
  for (const s of stencilMeshes) {
    scene.remove(s.mesh);
    s.mesh.material.dispose();
  }
  stencilMeshes.length = 0;
  stencilAnimStart = null;
}

function startStencilAnim3D() {
  if (!selectedCell || !blockSelect.value) return;
  const block = sten.blocks[blockSelect.value];
  if (!block) return;
  clearStencilMeshes();
  const [cx, cy, cz] = selectedCell;
  const readTargets = stencilTargetsFor3D(block.reads, cx, cy, cz);
  const writeTargets = stencilTargetsFor3D(block.writes, cx, cy, cz);
  // Cube slightly larger than the node cube so it's visible around /
  // through the underlying colour. depthWrite: false keeps transparent
  // blending from occluding other translucent targets.
  const overlayGeom = new THREE.BoxGeometry(
    CELL_CUBE_SIZE + 0.08, CELL_CUBE_SIZE + 0.08, CELL_CUBE_SIZE + 0.08);
  function addTargets(targets, color, phase) {
    for (const [x, y, z] of targets) {
      const mat = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0, depthWrite: false });
      const mesh = new THREE.Mesh(overlayGeom, mat);
      mesh.position.set(x + 0.5, y + 0.5, z + 0.5);
      mesh.renderOrder = 10;  // draw on top of the NC meshes
      scene.add(mesh);
      stencilMeshes.push({ mesh, phase });
    }
  }
  addTargets(readTargets, STENCIL_READ_COLOR, 'read');
  addTargets(writeTargets, STENCIL_WRITE_COLOR, 'write');
  stencilAnimStart = performance.now();
}

function updateStencilAnim(now) {
  if (stencilAnimStart == null) return;
  const elapsed = now - stencilAnimStart;
  const phase = STENCIL_ANIM_MS / 4;
  let readA = 0, writeA = 0;
  if (elapsed < phase)              readA = elapsed / phase;
  else if (elapsed < 2 * phase)     readA = 1 - (elapsed - phase) / phase;
  else if (elapsed < 3 * phase)     writeA = (elapsed - 2 * phase) / phase;
  else if (elapsed < 4 * phase)     writeA = 1 - (elapsed - 3 * phase) / phase;
  else { clearStencilMeshes(); return; }
  const rs = readA * STENCIL_PEAK_ALPHA;
  const ws = writeA * STENCIL_PEAK_ALPHA;
  for (const s of stencilMeshes) {
    s.mesh.material.opacity = (s.phase === 'read') ? rs : ws;
  }
}

// ===== Keyboard fly-through =====
const keys = new Set();
window.addEventListener('keydown', (e) => {
  const t = e.target;
  if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === 'r' || k === '0') { resetView(); e.preventDefault(); return; }
  if (e.key === '+' || e.key === '=') { dolly(1.25); e.preventDefault(); return; }
  if (e.key === '-' || e.key === '_') { dolly(1 / 1.25); e.preventDefault(); return; }
  if (e.key === ' ') { startStencilAnim3D(); e.preventDefault(); return; }
  keys.add(k);
});
window.addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
window.addEventListener('blur', () => keys.clear());

function applyKeyboardFly(dt) {
  if (keys.size === 0) return;
  const baseSpeed = Math.max(Nx, Ny, Nz) * 0.6;  // cells per second
  const speed = baseSpeed * dt * (keys.has('shift') ? 2.5 : 1);
  const forward = new THREE.Vector3();
  camera.getWorldDirection(forward);
  forward.y = 0;
  if (forward.lengthSq() < 1e-6) forward.set(0, 0, -1);
  forward.normalize();
  const right = new THREE.Vector3()
    .crossVectors(forward, new THREE.Vector3(0, 1, 0))
    .normalize();
  const delta = new THREE.Vector3();
  if (keys.has('w')) delta.addScaledVector(forward, speed);
  if (keys.has('s')) delta.addScaledVector(forward, -speed);
  if (keys.has('d')) delta.addScaledVector(right, speed);
  if (keys.has('a')) delta.addScaledVector(right, -speed);
  if (keys.has('e')) delta.y += speed;
  if (keys.has('q')) delta.y -= speed;
  if (delta.lengthSq() === 0) return;
  camera.position.add(delta);
  controls.target.add(delta);
}

// ===== Animate =====
const resizeObserver = new ResizeObserver(sizeCanvas);
resizeObserver.observe(wrap);

let lastT = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  applyKeyboardFly(dt);
  controls.update();
  updateZoomLabel();
  processPendingHover();  // at most one raycast per frame
  updateStencilAnim(now);
  renderer.render(scene, camera);
  renderAxisGizmo();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</body>
</html>`;
    }
}


async function showInteractivePreview(context: vscode.ExtensionContext) {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== 'gelb') {
        vscode.window.showErrorMessage(
            'Open a .gelb file first, then run this command.');
        return;
    }
    if (await blockedByErrors(editor.document)) return;
    if (activeInteractive) {
        activeInteractive.panel.dispose();
    }
    activeInteractive = new InteractivePreview(
        editor.document, context.extensionUri);
    activeInteractive.refresh();

    // Same reason as in showSourcePreview: pin the sidebar's Program
    // Structure and Run views to this document, so focusing the webview
    // doesn't blank them out.
    programStructureProvider?.setCurrentDocument(editor.document);
    runProvider?.setCurrentDocument(editor.document);
}
