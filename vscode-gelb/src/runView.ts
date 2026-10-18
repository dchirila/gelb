/**
 * "Run" TreeView for the GeLB sidebar, between Program Structure and
 * Other Diagnostics: runs the .gelb file that Program Structure shows
 * through gelb-run, as a VS Code task the extension owns.
 *
 * The everyday parameters are rows that edit on click (time steps,
 * write-every, constant overrides, seed when the program calls
 * random(), backend, the viewer toggle, the output folder); every
 * other gelb-run flag is for the command line, which the "GeLB Run"
 * output shows for each run. Values are remembered per file in the
 * workspace state. The arguments are built by the pure functions in
 * runCommand.ts; one run at a time, Stop and the states of the Status
 * row are runController.ts; the task is runExecutor.ts.
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { parseGelbSymbols } from './gelbParser';
import {
    BACKENDS,
    Backend,
    DEFAULT_BACKEND,
    RunParams,
    UnquotableError,
    buildRunArgs,
    buildRunCommandLine,
    displayRunCommandLine,
    isBackend,
    outputFileFor,
    quoteForPosixShell,
    resolveOutputFolderSetting,
    runLensLine,
    sourceCallsRandom,
} from './runCommand';
import { RunController, RunPhase, RunRequest, RunUi } from './runController';
import { RunSpec, TaskRunExecutor } from './runExecutor';
import { reportMissingTool, toolCommand } from './toolCommand';

const RUN_IN_PROGRESS_KEY = 'gelb.runInProgress';
/** Workspace state: the run going in this window, if any, so that the
 *  next window can say what became of it. */
const LIVE_RUN_KEY = 'gelb.run.live';

/** A request's phase in a sentence: "run #3 is still <...>". */
const PHASE_WORDS: Record<RunPhase, string> = {
    preparing: 'being prepared',
    launching: 'being launched',
    starting: 'starting',
    running: 'running',
    unconfirmed: 'unconfirmed',
    stopping: 'stopping',
    ended: 'ending',
};

type RowId =
    | 'file' | 'timeSteps' | 'writeEvery' | 'constants' | 'seed'
    | 'backend' | 'view' | 'outputFolder'
    | 'run' | 'stop' | 'status' | 'openFolder' | 'openOutput';

/** What is stored per file under `gelb.run:<fsPath>`. Every field is
 *  optional: an absent one falls back to the settings, so a lab that
 *  changes `gelb.runDefaultTimeSteps` moves every file not yet edited. */
interface StoredRunState {
    timeSteps?: number;
    writeEvery?: number;
    defines?: [string, string][];
    seed?: number;
    backend?: Backend;
    view?: boolean;
    /** Absolute folder chosen in the Output folder row. */
    outputFolder?: string;
    /** The .nc the last successful Run of this file wrote. */
    lastOutput?: string;
}

/* ------------------------------------------------------------------ */
/*  Tree item                                                         */
/* ------------------------------------------------------------------ */

export class RunItem extends vscode.TreeItem {
    constructor(
        public readonly rowId: RowId,
        public readonly uri: vscode.Uri,
        label: string,
        icon: string | vscode.ThemeIcon,
        command: vscode.Command,
        description?: string,
        tooltip?: string,
        contextValue?: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.description = description;
        this.iconPath = typeof icon === 'string'
            ? new vscode.ThemeIcon(icon) : icon;
        this.command = command;
        this.tooltip = tooltip;
        this.contextValue = contextValue ?? `gelb.run.${rowId}`;
    }
}

/* ------------------------------------------------------------------ */
/*  Tree data provider                                                */
/* ------------------------------------------------------------------ */

export class RunProvider implements vscode.TreeDataProvider<RunItem> {
    private _onDidChange = new vscode.EventEmitter<RunItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChange.event;

    private refreshTimer: NodeJS.Timeout | undefined;

    /** Sticky document, fed by the same events as Program Structure. */
    private currentDocument: vscode.TextDocument | undefined;

    /** The "GeLB Run" output: each request, step by step. */
    private readonly output: vscode.OutputChannel;
    private readonly executor: TaskRunExecutor;
    private readonly controller: RunController<RunSpec>;
    /** Set by gelb.internal.runTestHooks (test mode only): queued
     *  answers, and what was shown and logged. */
    private hooks: {
        answers: (string | undefined)[]; messages: string[]; log: string[];
    } | undefined;

    constructor(private readonly context: vscode.ExtensionContext) {
        this.output = vscode.window.createOutputChannel('GeLB Run');
        this.executor = new TaskRunExecutor();
        this.controller = new RunController(this.executor, this.runUi);
    }

    /** How long a launched run may take to report its start. */
    get startTimeoutMs(): number {
        return this.controller.timeouts.startMs;
    }

    set startTimeoutMs(ms: number) {
        this.controller.timeouts.startMs = ms;
    }

    /* ---------- document tracking (mirrors ProgramStructureProvider) */

    getCurrentDocument(): vscode.TextDocument | undefined {
        return this.currentDocument;
    }

    setCurrentDocument(doc: vscode.TextDocument | undefined): void {
        if (doc && doc.languageId !== 'gelb') return;
        if (this.currentDocument?.uri.toString() === doc?.uri.toString()) {
            return;
        }
        this.currentDocument = doc;
        this.refresh();
    }

    refresh(): void {
        this._onDidChange.fire(undefined);
    }

    refreshDebounced(delayMs = 250): void {
        if (this.refreshTimer) clearTimeout(this.refreshTimer);
        this.refreshTimer = setTimeout(() => this.refresh(), delayMs);
    }

    /** The document the rows describe: the active .gelb editor, else
     *  the sticky one (same precedence as Program Structure). */
    private shownDocument(): vscode.TextDocument | undefined {
        const ed = vscode.window.activeTextEditor;
        if (ed && ed.document.languageId === 'gelb') return ed.document;
        return this.currentDocument;
    }

    /** Resolve a command's target: an explicit URI (CodeLens, editor
     *  title, a row) or the shown document. */
    private async targetDocument(
        arg?: unknown,
    ): Promise<vscode.TextDocument | undefined> {
        let uri: vscode.Uri | undefined;
        if (arg instanceof vscode.Uri) uri = arg;
        else if (arg instanceof RunItem) uri = arg.uri;
        if (uri) {
            const open = vscode.workspace.textDocuments.find(
                d => d.uri.toString() === uri!.toString());
            return open ?? vscode.workspace.openTextDocument(uri);
        }
        const doc = this.shownDocument();
        if (!doc) {
            vscode.window.showErrorMessage(
                'Open a .gelb file first, then run this command.');
        }
        return doc;
    }

    /* ---------- state */

    private stateKey(file: string): string {
        return `gelb.run:${file}`;
    }

    private loadState(file: string): StoredRunState {
        const raw = this.context.workspaceState.get<StoredRunState>(
            this.stateKey(file)) ?? {};
        // Defensive: the state is JSON from an earlier session.
        const st: StoredRunState = {};
        if (isCount(raw.timeSteps, 1)) st.timeSteps = raw.timeSteps;
        if (isCount(raw.writeEvery, 1)) st.writeEvery = raw.writeEvery;
        if (Array.isArray(raw.defines)) {
            st.defines = raw.defines.filter(
                (p): p is [string, string] => Array.isArray(p)
                    && typeof p[0] === 'string' && typeof p[1] === 'string');
        }
        if (isCount(raw.seed, 0)) st.seed = raw.seed;
        if (isBackend(raw.backend)) st.backend = raw.backend;
        if (typeof raw.view === 'boolean') st.view = raw.view;
        if (typeof raw.outputFolder === 'string') {
            st.outputFolder = raw.outputFolder;
        }
        if (typeof raw.lastOutput === 'string') st.lastOutput = raw.lastOutput;
        return st;
    }

    private async saveState(
        file: string, patch: Partial<StoredRunState>,
    ): Promise<void> {
        const st: StoredRunState = { ...this.loadState(file), ...patch };
        for (const k of Object.keys(patch) as (keyof StoredRunState)[]) {
            if (patch[k] === undefined) delete st[k];
        }
        await this.context.workspaceState.update(this.stateKey(file), st);
        this.refresh();
    }

    /** The folder the file runs in when no row override is stored:
     *  `gelb.runOutputFolder`, else next to the source. */
    private defaultOutputFolder(doc: vscode.TextDocument): string {
        const cfg = vscode.workspace.getConfiguration('gelb', doc.uri);
        const ws = vscode.workspace.getWorkspaceFolder(doc.uri);
        return resolveOutputFolderSetting(
            cfg.get<string>('runOutputFolder', ''),
            ws?.uri.fsPath, os.homedir(),
        ) ?? path.dirname(doc.uri.fsPath);
    }

    /** The parameters a Run of `doc` uses right now. */
    private paramsFor(doc: vscode.TextDocument): RunParams {
        const file = doc.uri.fsPath;
        const st = this.loadState(file);
        const cfg = vscode.workspace.getConfiguration('gelb', doc.uri);
        const cfgCount = (key: string, dflt: number) => {
            const v = cfg.get<number>(key, dflt);
            return isCount(v, 1) ? v : dflt;
        };
        return {
            timeSteps: st.timeSteps ?? cfgCount('runDefaultTimeSteps', 1000),
            writeEvery: st.writeEvery ?? cfgCount('runDefaultWriteEvery', 100),
            defines: st.defines ?? [],
            // A stored seed is only emitted while the row is visible.
            seed: sourceCallsRandom(doc.getText()) ? st.seed : undefined,
            backend: st.backend ?? DEFAULT_BACKEND,
            view: st.view ?? true,
            outputFolder: st.outputFolder ?? this.defaultOutputFolder(doc),
        };
    }

    /* ---------- rows */

    getTreeItem(element: RunItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: RunItem): vscode.ProviderResult<RunItem[]> {
        if (element) return [];
        const doc = this.shownDocument();
        if (!doc) return [];   // → the viewsWelcome text
        const uri = doc.uri;
        const file = uri.fsPath;
        const p = this.paramsFor(doc);
        const st = this.loadState(file);
        const folder = p.outputFolder ?? path.dirname(file);
        const edit = (id: RowId): vscode.Command => ({
            command: 'gelb.editRunParameter',
            title: 'Edit',
            arguments: [id, uri],
        });
        const act = (command: string): vscode.Command => ({
            command, title: command, arguments: [uri],
        });

        const header = new RunItem(
            'file', uri, path.basename(file), vscode.ThemeIcon.File,
            { command: 'vscode.open', title: 'Open', arguments: [uri] },
            undefined, file);
        header.resourceUri = uri;

        const rows: RunItem[] = [header];
        rows.push(new RunItem('timeSteps', uri, 'Time steps', 'symbol-numeric',
            edit('timeSteps'), String(p.timeSteps),
            'gelb-run -n: number of time steps. Click to edit.'));
        rows.push(new RunItem('writeEvery', uri, 'Write every', 'symbol-numeric',
            edit('writeEvery'), String(p.writeEvery),
            'gelb-run -w: write the gauges to the .nc every N steps. Click to edit.'));
        rows.push(new RunItem('constants', uri, 'Constants', 'symbol-constant',
            edit('constants'),
            p.defines.length
                ? p.defines.map(([k, v]) => `${k}=${v}`).join('  ')
                : 'none',
            'gelb-run -D NAME=VALUE: override constants of global_constants. '
                + 'Click to pick one.',
            p.defines.length ? 'gelb.run.constants' : 'gelb.run.constants.none'));
        if (sourceCallsRandom(doc.getText())) {
            rows.push(new RunItem('seed', uri, 'Seed', 'symbol-numeric',
                edit('seed'),
                st.seed === undefined ? '(clock)' : String(st.seed),
                'gelb-run -s: fixed seed for random(); (clock) seeds from '
                    + 'the system clock. Click to edit.'));
        }
        rows.push(new RunItem('backend', uri, 'Backend', 'server-process',
            edit('backend'), p.backend,
            'gelb-run -b: code generator and compiler. Click to choose.'));
        rows.push(new RunItem('view', uri, 'Open viewer',
            p.view ? 'eye' : 'eye-closed', edit('view'),
            p.view ? 'on' : 'off',
            'gelb-run --view: open gelb-view on the output when the run '
                + 'ends. Click to toggle.'));
        rows.push(new RunItem('outputFolder', uri, 'Output folder', 'folder',
            edit('outputFolder'), describeFolder(folder, file),
            `The run's working directory, where ${path.basename(outputFileFor(file, folder))} `
                + `lands:\n${folder}\nClick to change.`));

        rows.push(new RunItem('run', uri, 'Run', 'play', act('gelb.run'),
            undefined,
            'Save the file and run it with gelb-run, as a task: its output in '
                + 'the terminal panel, each step in the "GeLB Run" output.'));
        rows.push(new RunItem('stop', uri, 'Stop', 'debug-stop',
            act('gelb.stopRun'), undefined,
            'Stop the run: Ctrl-C to gelb-run and what it started (compiler, '
                + 'simulation, viewer), then end its task.'));
        rows.push(this.statusRow(uri));
        rows.push(new RunItem('openFolder', uri, 'Open output folder',
            'folder-opened', act('gelb.openRunOutputFolder'), undefined,
            folder));
        const nc = st.lastOutput ?? outputFileFor(file, folder);
        const ncTime = mtimeOf(nc);
        rows.push(new RunItem('openOutput', uri, 'Open last output in viewer',
            'graph', act('gelb.openLastOutputInViewer'), undefined,
            ncTime === undefined ? `${nc}\n(not written yet)`
                : `${nc}\nwritten ${new Date(ncTime).toLocaleString()}`));
        return rows;
    }

    /* ---------- editing */

    async editParameter(rowId: RowId, uri?: vscode.Uri): Promise<void> {
        const doc = await this.targetDocument(uri);
        if (!doc) return;
        const file = doc.uri.fsPath;
        const p = this.paramsFor(doc);
        const st = this.loadState(file);
        switch (rowId) {
            case 'timeSteps': {
                const n = await askInteger({
                    title: 'Time steps (gelb-run -n)',
                    value: p.timeSteps,
                    min: 1,
                    warn: v => v < p.writeEvery
                        ? `Fewer than "Write every" (${p.writeEvery}): `
                          + 'gelb-run then writes only the initial state.'
                        : undefined,
                });
                if (typeof n === 'number') await this.saveState(file, { timeSteps: n });
                break;
            }
            case 'writeEvery': {
                const n = await askInteger({
                    title: 'Write every (gelb-run -w)',
                    value: p.writeEvery,
                    min: 1,
                    warn: v => v > p.timeSteps
                        ? `More than the time steps (${p.timeSteps}): `
                          + 'gelb-run then writes only the initial state.'
                        : undefined,
                });
                if (typeof n === 'number') await this.saveState(file, { writeEvery: n });
                break;
            }
            case 'seed': {
                const n = await askInteger({
                    title: 'Seed for random() (gelb-run -s)',
                    prompt: 'A non-negative integer; empty seeds from the clock.',
                    value: st.seed,
                    min: 0,
                    allowEmpty: true,
                });
                if (n === null) await this.saveState(file, { seed: undefined });
                else if (n !== undefined) await this.saveState(file, { seed: n });
                break;
            }
            case 'constants':
                await this.editConstants(doc, p.defines);
                break;
            case 'backend': {
                const pick = await vscode.window.showQuickPick(
                    BACKENDS.map(b => ({
                        label: b.id,
                        description: b.id === p.backend ? '(current)' : '',
                        detail: b.description,
                        id: b.id,
                    })),
                    { title: 'Backend (gelb-run -b)' });
                if (pick) {
                    await this.saveState(file, {
                        backend: pick.id === DEFAULT_BACKEND ? undefined : pick.id,
                    });
                }
                break;
            }
            case 'view':
                await this.saveState(file, { view: !p.view });
                break;
            case 'outputFolder':
                await this.editOutputFolder(doc);
                break;
            default:
                break;
        }
    }

    private async editConstants(
        doc: vscode.TextDocument, defines: [string, string][],
    ): Promise<void> {
        const file = doc.uri.fsPath;
        const constants = parseGelbSymbols(doc.getText())
            .filter(s => s.kind === 'global_constants')
            .flatMap(s => s.children)
            .filter(c => c.kind === 'constant');
        const overrides = new Map(defines);

        type Item = vscode.QuickPickItem & {
            action: 'edit' | 'clear' | 'free';
            name?: string;
            detailText?: string;
        };
        const items: Item[] = [];
        for (const c of constants) {
            const ov = overrides.get(c.name);
            items.push({
                label: ov === undefined ? c.name : `$(edit) ${c.name}`,
                description: (c.detail ?? '')
                    + (ov === undefined ? '' : `   → ${ov}`),
                action: 'edit', name: c.name, detailText: c.detail,
            });
        }
        // Overrides of names the file no longer declares stay removable.
        for (const [name, value] of defines) {
            if (constants.some(c => c.name === name)) continue;
            items.push({
                label: `$(edit) ${name}`,
                description: `not in this file   → ${value}`,
                action: 'edit', name,
            });
        }
        if (items.length) {
            items.push({ label: '', kind: vscode.QuickPickItemKind.Separator,
                action: 'free' });
        }
        if (defines.length) {
            items.push({ label: '$(clear-all) Clear all overrides',
                action: 'clear' });
        }
        items.push({ label: '$(pencil) Type NAME=VALUE...', action: 'free' });

        const pick = await vscode.window.showQuickPick(items, {
            title: 'Constant overrides (gelb-run -D NAME=VALUE)',
            placeHolder: constants.length
                ? 'Pick a constant to override'
                : 'No constants found in global_constants; type NAME=VALUE',
            matchOnDescription: true,
        });
        if (!pick) return;

        const store = async (next: Map<string, string>) =>
            this.saveState(file, {
                defines: next.size ? [...next.entries()] : undefined,
            });

        if (pick.action === 'clear') {
            await store(new Map());
            return;
        }
        if (pick.action === 'free') {
            const text = await vscode.window.showInputBox({
                title: 'Constant override (gelb-run -D)',
                prompt: 'NAME=VALUE; the value is passed to gelbc as written.',
                placeHolder: 'N=257',
                validateInput: v => {
                    const m = /^\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*$/.exec(v);
                    if (!m || !m[2]) return 'Expected NAME=VALUE, e.g. N=257';
                    return quotingProblem(`${m[1]}=${m[2]}`);
                },
            });
            if (text === undefined) return;
            const m = /^\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*$/.exec(text)!;
            await store(new Map(overrides).set(m[1], m[2]));
            return;
        }

        const name = pick.name!;
        const sourceValue = pick.detailText?.replace(/^.*?=\s*/, '');
        const value = await vscode.window.showInputBox({
            title: `Override ${name} (gelb-run -D ${name}=...)`,
            prompt: (pick.detailText ? `In the file: ${pick.detailText}. ` : '')
                + 'Empty removes the override.',
            value: overrides.get(name) ?? sourceValue ?? '',
            validateInput: v => v.trim()
                ? quotingProblem(`${name}=${v.trim()}`) : undefined,
        });
        if (value === undefined) return;
        const next = new Map(overrides);
        if (value.trim()) next.set(name, value.trim());
        else next.delete(name);
        await store(next);
    }

    private async editOutputFolder(doc: vscode.TextDocument): Promise<void> {
        const file = doc.uri.fsPath;
        const cfg = vscode.workspace.getConfiguration('gelb', doc.uri);
        const setting = cfg.get<string>('runOutputFolder', '').trim();
        type Item = vscode.QuickPickItem & { action: 'source' | 'setting' | 'choose' };
        const items: Item[] = [
            { label: "$(file) Use the source file's folder",
              description: describeHome(path.dirname(file)), action: 'source' },
        ];
        if (setting) {
            items.push({ label: '$(settings-gear) Use gelb.runOutputFolder',
                description: setting, action: 'setting' });
        }
        items.push({ label: '$(folder-opened) Choose a folder...',
            action: 'choose' });
        const pick = await vscode.window.showQuickPick(items,
            { title: 'Output folder (where gelb-run runs and writes the .nc)' });
        if (!pick) return;
        if (pick.action === 'setting') {
            await this.saveState(file, { outputFolder: undefined });
        } else if (pick.action === 'source') {
            // Without the setting the default already is the source folder.
            await this.saveState(file, {
                outputFolder: setting ? path.dirname(file) : undefined,
            });
        } else {
            const current = this.paramsFor(doc).outputFolder;
            const chosen = await vscode.window.showOpenDialog({
                canSelectFolders: true,
                canSelectFiles: false,
                canSelectMany: false,
                defaultUri: current && fs.existsSync(current)
                    ? vscode.Uri.file(current) : undefined,
                openLabel: 'Run here',
                title: 'Output folder for gelb-run',
            });
            if (!chosen || chosen.length === 0) return;
            const dir = chosen[0].fsPath;
            await this.saveState(file, {
                outputFolder: !setting && dir === path.dirname(file)
                    ? undefined : dir,
            });
        }
    }

    async clearConstants(arg?: unknown): Promise<void> {
        const doc = await this.targetDocument(arg);
        if (doc) await this.saveState(doc.uri.fsPath, { defines: undefined });
    }

    /* ---------- running */

    private setRunning(on: boolean): void {
        vscode.commands.executeCommand('setContext', RUN_IN_PROGRESS_KEY, on);
    }

    /**
     * Run the file: an explicit target (CodeLens, editor title, a row)
     * or the shown document, fixed at the click, so switching editors
     * while the run is prepared does not change what runs. One run at a
     * time: see runController.ts for what a click does meanwhile.
     */
    run(arg?: unknown): Promise<void> {
        let uri: vscode.Uri | undefined;
        if (arg instanceof vscode.Uri) uri = arg;
        else if (arg instanceof RunItem) uri = arg.uri;
        else uri = this.shownDocument()?.uri;
        if (!uri) {
            void vscode.window.showErrorMessage(
                'Open a .gelb file first, then run this command.');
            return Promise.resolve();
        }
        const target = uri;
        return this.controller.run(path.basename(target.fsPath),
            (req) => this.prepare(req, target));
    }

    stop(): Promise<void> {
        return this.controller.stop();
    }

    /**
     * Everything the run needs, taken now: the saved file, its
     * parameters, the runner and the output folder (created). Undefined
     * when there is nothing to run (the user has been told why).
     */
    private async prepare(
        req: RunRequest<RunSpec>, uri: vscode.Uri,
    ): Promise<RunSpec | undefined> {
        const doc = vscode.workspace.textDocuments.find(
            d => d.uri.toString() === uri.toString())
            ?? await vscode.workspace.openTextDocument(uri);
        if (doc.languageId !== 'gelb') {
            void this.message('error', 'GeLB: the Run command needs a .gelb file.');
            return undefined;
        }
        if (doc.isUntitled || doc.uri.scheme !== 'file') {
            void this.message('error',
                'GeLB: save the file to disk first; gelb-run reads it from there.');
            return undefined;
        }
        if (doc.isDirty && !(await doc.save())) {
            void this.message('error',
                `GeLB: could not save ${path.basename(doc.uri.fsPath)}; not running it.`);
            return undefined;
        }
        if (req.cancelled) return undefined;
        this.setCurrentDocument(doc);

        const file = doc.uri.fsPath;
        const tool = toolCommand('gelb-run', doc.uri);
        if (!tool.argv) {
            this.hooks?.messages.push(tool.error);
            void reportMissingTool('gelb-run', tool.error);
            return undefined;
        }
        const runner = tool.argv[0];
        // A bare name is left to the task shell's PATH; a path must exist.
        const viaShell = !path.isAbsolute(runner);
        if (!viaShell && !isExecutableFile(runner)) {
            const open = 'Open Settings';
            void this.message('warning',
                `GeLB Run disabled — "${runner}" is not an executable file.\n`
                + 'Set the "gelb.gelbRunCommand" setting to the gelb-run you '
                + 'use, or leave it empty to use the scripts/gelb-run of the '
                + 'GeLB source checkout (or the gelb-run of the GeLB '
                + 'installation) the file is in.',
                open).then((choice) => {
                if (choice === open) {
                    vscode.commands.executeCommand(
                        'workbench.action.openSettings', 'gelb.gelbRunCommand');
                }
            });
            return undefined;
        }

        const params = this.paramsFor(doc);
        const folder = params.outputFolder ?? path.dirname(file);
        try {
            fs.mkdirSync(folder, { recursive: true });
        } catch (e: any) {
            throw new Error(`cannot create the output folder ${folder}: ${e.message}`);
        }
        let args: string[];
        let commandLine: string;
        try {
            args = buildRunArgs(file, params);
            commandLine = viaShell
                ? buildRunCommandLine(runner, file, params)
                : displayRunCommandLine(runner, file, params);
        } catch (e: any) {
            if (e instanceof UnquotableError || e instanceof RangeError) {
                throw new Error(`${e.message}. Change that value (or rename the `
                    + 'path) and run again');
            }
            throw e;
        }
        const output = outputFileFor(file, folder);
        const log = (text: string) => this.runUi.log(req.id, text);
        log(`file ${file}`);
        log(`backend ${params.backend}; working directory ${folder}`);
        log(`runner ${runner}, from ${tool.from}`
            + (viaShell ? '; run through the task shell' : ''));
        log(`command: ${commandLine}`);
        return {
            file, folder, runner, runnerFrom: tool.from, viaShell, args,
            commandLine, backend: params.backend, output,
            outputMtimeBefore: mtimeOf(output),
        };
    }

    /** The adapter runController.ts reports through. */
    private readonly runUi: RunUi<RunSpec> = {
        log: (id, text) => {
            const line = `${id === undefined ? '' : `#${id} `}${text}`;
            this.hooks?.log.push(line);
            this.output.appendLine(`${timestamp()} ${line}`);
        },
        changed: () => {
            this.setRunning(this.controller.busy);
            const r = this.controller.request;
            void this.context.workspaceState.update(LIVE_RUN_KEY,
                r ? { id: r.id, label: r.label } : undefined);
            this.refresh();
        },
        confirmStopAndRun: async (cur, next) => {
            const stopAndRun = 'Stop and Run';
            const choice = await this.ask(
                `A GeLB run is still going: ${cur.label} (#${cur.id}).`,
                (cur.phase === 'unconfirmed'
                    ? 'Its start or stop was never confirmed, so it may still be going. '
                    : 'It is compiling, simulating, or waiting for its viewer '
                        + 'window to close. ')
                    + `Stop it and run ${next} instead?`,
                stopAndRun);
            return choice === stopAndRun;
        },
        coalesced: (cur, next) => {
            const why = cur
                ? `run #${cur.id} (${cur.label}) is still ${PHASE_WORDS[cur.phase]}`
                : 'a question about the current run is open';
            this.hooks?.messages.push(`coalesced: ${next}`);
            vscode.window.setStatusBarMessage(`GeLB: ${why}; Run ignored.`, 5000);
        },
        unconfirmed: (req, ms) => {
            this.notify('warning', req,
                `GeLB: run #${req.id} (${req.label}) has not reported its start `
                + `after ${ms / 1000} s. It may still start; Stop cancels it.`);
        },
        ended: (req) => this.runEnded(req),
        launchFailed: (req, e) => {
            this.notify('error', req,
                `GeLB: run #${req.id} (${req.label}) could not be launched: ${errorText(e)}.`);
        },
        prepareFailed: (req, e) => {
            this.notify('error', undefined, `GeLB: ${errorText(e)}.`);
        },
        stopUnconfirmed: (req, ms) => {
            this.notify('error', req,
                `GeLB: run #${req.id} (${req.label}) did not stop within ${ms / 1000} s. `
                + "A viewer window may still be open: close it, or close the run's terminal.");
        },
        nothingToStop: () => {
            void this.message('info', 'GeLB: no run is going.');
        },
    };

    /** A run ended on its own: record a new output, or say what went
     *  wrong. A failed run leaves the last output as it was, so an older
     *  .nc never looks like this run's result. */
    private runEnded(req: RunRequest<RunSpec>): void {
        const spec = req.spec;
        if (!spec) return;
        const mtime = mtimeOf(spec.output);
        const wrote = mtime !== undefined && mtime !== spec.outputMtimeBefore;
        if (req.exitCode === 0) {
            if (wrote) {
                this.runUi.log(req.id, `wrote ${spec.output}`);
                void this.saveState(spec.file, { lastOutput: spec.output });
            } else {
                this.runUi.log(req.id, `no new ${path.basename(spec.output)}`);
            }
            return;
        }
        if (mtime !== undefined && !wrote) {
            this.runUi.log(req.id, `${spec.output} is from an earlier run`);
        }
        if (req.exitCode === 127 && spec.viaShell) {
            const text = `the task shell could not find "${spec.runner}". Open the `
                + '.gelb file (or a workspace) inside a GeLB source checkout or a '
                + 'GeLB installation, put gelb-run on the PATH, or set '
                + '"gelb.gelbRunCommand"';
            this.hooks?.messages.push(text);
            void reportMissingTool('gelb-run', text);
            return;
        }
        this.notify('error', req,
            `GeLB: run #${req.id} (${req.label}) ${describeEnd(req.exitCode, req.pid)}.`);
    }

    /** A notification (recorded in tests). */
    private message(
        level: 'info' | 'warning' | 'error', text: string, ...items: string[]
    ): Thenable<string | undefined> {
        this.hooks?.messages.push(text);
        const show = level === 'error' ? vscode.window.showErrorMessage
            : level === 'warning' ? vscode.window.showWarningMessage
                : vscode.window.showInformationMessage;
        return show(text, ...items);
    }

    /** A notification with the ways to look closer, not awaited. */
    private notify(
        level: 'warning' | 'error', req: RunRequest<RunSpec> | undefined, text: string,
    ): void {
        const terminal = 'Show Terminal';
        const log = 'Show Log';
        const items = req?.spec ? [terminal, log] : [log];
        void this.message(level, text, ...items).then((choice) => {
            if (choice === terminal && req) this.revealTerminal(req);
            else if (choice === log) this.output.show(true);
        });
    }

    /** A modal question; in tests with hooks set, the next queued answer. */
    private async ask(
        message: string, detail: string, ...items: string[]
    ): Promise<string | undefined> {
        if (this.hooks) {
            this.hooks.messages.push(message);
            return this.hooks.answers.shift();
        }
        return vscode.window.showWarningMessage(message, { modal: true, detail }, ...items);
    }

    /** Show the terminal of `req`'s task: VS Code names it after the
     *  task. Presentation only; the run is tracked by its execution.
     *  Once a later run has reused the terminal, the log instead. */
    private revealTerminal(req: RunRequest<RunSpec>): void {
        const name = req.spec ? TaskRunExecutor.taskName(req.spec.file, req.id) : undefined;
        const t = vscode.window.terminals.find(x => x.name === name);
        if (t) t.show(true);
        else this.output.show(true);
    }

    showLog(): void {
        this.output.show(true);
    }

    /** The Status row: the state of the current (else the last) run. */
    private statusRow(uri: vscode.Uri): RunItem {
        const state = this.controller.state;
        const req = this.controller.shown;
        const other = req && req.spec && req.spec.file !== uri.fsPath
            ? ` (${req.label})` : '';
        const id = req ? `#${req.id}${other} ` : '';
        let text: string;
        let icon: string;
        switch (state) {
            case 'starting':
                text = `${id}starting`;
                icon = 'loading~spin';
                break;
            case 'running':
                text = `${id}running`;
                icon = 'sync~spin';
                break;
            case 'stopping':
                text = `${id}stopping`;
                icon = 'loading~spin';
                break;
            case 'failed':
                text = `${id}${req?.failure ?? 'failed'}`;
                icon = 'error';
                break;
            default:
                if (req?.stopRequested && req.execution) {
                    text = `${id}stopped`;
                    icon = 'circle-slash';
                } else if (req?.exitCode === 0) {
                    text = `${id}finished`;
                    icon = 'pass';
                } else {
                    text = 'idle';
                    icon = 'circle-large-outline';
                }
        }
        return new RunItem('status', uri, 'Status', icon,
            { command: 'gelb.showRunLog', title: 'Show Run Log' }, text,
            'The current or last run, numbered as in the "GeLB Run" output. '
                + 'Click for that log.');
    }

    /** A GeLB run task still going when the extension starts (a window
     *  reload): followed as the current run, so Stop can end it. When
     *  there is none but the last window had a run going, VS Code ended
     *  it with that window: the Status row says so. */
    private adoptRunning(): void {
        const exec = this.executor.ownExecutions()[0];
        const live = this.context.workspaceState.get<{ id: number; label: string }>(LIVE_RUN_KEY);
        if (!exec) {
            if (live && typeof live.id === 'number' && typeof live.label === 'string') {
                this.controller.noteLost(live.id, live.label,
                    'ended with the window (reloaded or closed)');
            }
            return;
        }
        const file = exec.task.definition.file;
        const label = typeof file === 'string' ? path.basename(file) : exec.task.name;
        const req = this.controller.adopt(label, l => this.executor.attach(exec, l));
        this.runUi.log(req.id, `found "${exec.task.name}" still going from before `
            + 'the window reload; Stop ends it');
    }

    /** Test mode only: what the Development Host tests check. */
    private statusForTests(file?: string): object {
        const describe = (r: RunRequest<RunSpec> | undefined) => r && {
            id: r.id, label: r.label, phase: r.phase, pid: r.pid,
            exitCode: r.exitCode, failure: r.failure,
            stopRequested: r.stopRequested, spec: r.spec,
        };
        return {
            state: this.controller.state,
            request: describe(this.controller.request),
            shown: describe(this.controller.shown),
            messages: this.hooks?.messages ?? [],
            log: this.hooks?.log ?? [],
            stored: file ? this.loadState(file) : undefined,
        };
    }

    async openOutputFolder(arg?: unknown): Promise<void> {
        const doc = await this.targetDocument(arg);
        if (!doc) return;
        const file = doc.uri.fsPath;
        const folder = this.paramsFor(doc).outputFolder ?? path.dirname(file);
        if (!fs.existsSync(folder)) {
            vscode.window.showWarningMessage(
                `GeLB: the output folder ${folder} does not exist yet; Run creates it.`);
            return;
        }
        // Finder, with this file's .nc selected when there is one.
        const nc = outputFileFor(file, folder);
        await vscode.commands.executeCommand('revealFileInOS',
            vscode.Uri.file(fs.existsSync(nc) ? nc : folder));
    }

    async openLastOutputInViewer(arg?: unknown): Promise<void> {
        const doc = await this.targetDocument(arg);
        if (!doc) return;
        const file = doc.uri.fsPath;
        const st = this.loadState(file);
        const folder = this.paramsFor(doc).outputFolder ?? path.dirname(file);
        const nc = st.lastOutput ?? outputFileFor(file, folder);
        if (!fs.existsSync(nc)) {
            vscode.window.showWarningMessage(
                `GeLB: ${nc} does not exist (yet). Run the file first.`);
            return;
        }
        const tool = toolCommand('gelb-view', doc.uri);
        if (!tool.argv) {
            await reportMissingTool('gelb-view', tool.error);
            return;
        }
        const [exe = '', ...cmdArgs] = tool.argv;
        const cmd = tool.argv.join(' ');
        const ws = vscode.workspace.getWorkspaceFolder(doc.uri);
        const cwd = ws?.uri.fsPath ?? path.dirname(file);
        try {
            const proc = cp.spawn(exe, [...cmdArgs, nc],
                { cwd, detached: true, stdio: 'ignore' });
            proc.on('error', (e) => vscode.window.showErrorMessage(
                `GeLB: could not start "${cmd}" (${e.message}). Set the `
                + '"gelb.gelbViewCommand" setting to the command that runs '
                + 'gelb-view, or leave it empty to find it.'));
            proc.unref();
        } catch (e: any) {
            vscode.window.showErrorMessage(
                `GeLB: could not start "${cmd}" (${e.message}).`);
        }
    }

    /* ---------- wiring */

    /** Commands, the task executor, the log and the CodeLens; everything
     *  the Run view needs besides the document-tracking handlers, which
     *  extension.ts shares with Program Structure. */
    register(): vscode.Disposable[] {
        this.setRunning(false);
        const subs: vscode.Disposable[] = [
            this.output,
            this.executor,
            { dispose: () => this.controller.dispose() },
            vscode.window.registerTreeDataProvider('gelbRun', this),
            vscode.commands.registerCommand('gelb.run',
                (arg?: unknown) => this.run(arg)),
            vscode.commands.registerCommand('gelb.stopRun',
                () => this.stop()),
            vscode.commands.registerCommand('gelb.showRunLog',
                () => this.showLog()),
            vscode.commands.registerCommand('gelb.editRunParameter',
                (id: RowId, uri?: vscode.Uri) => this.editParameter(id, uri)),
            vscode.commands.registerCommand('gelb.clearRunConstants',
                (arg?: unknown) => this.clearConstants(arg)),
            vscode.commands.registerCommand('gelb.openRunOutputFolder',
                (arg?: unknown) => this.openOutputFolder(arg)),
            vscode.commands.registerCommand('gelb.openLastOutputInViewer',
                (arg?: unknown) => this.openLastOutputInViewer(arg)),
            // Not contributed (no palette entry): the CodeLens target.
            vscode.commands.registerCommand('gelb.showRunView',
                async (uri?: vscode.Uri) => {
                    const doc = await this.targetDocument(uri);
                    if (doc) this.setCurrentDocument(doc);
                    await vscode.commands.executeCommand(
                        'workbench.view.extension.gelb-sidebar');
                    await vscode.commands.executeCommand('gelbRun.focus');
                }),
            vscode.workspace.onDidChangeConfiguration((e) => {
                if (e.affectsConfiguration('gelb')) this.refresh();
            }),
            vscode.languages.registerCodeLensProvider(
                { language: 'gelb' }, new RunCodeLensProvider()),
        ];
        if (this.context.extensionMode === vscode.ExtensionMode.Test) {
            // For the Extension Development Host tests (test/suite):
            // questions answered from a queue, messages recorded, state.
            subs.push(
                vscode.commands.registerCommand('gelb.internal.runTestHooks',
                    async (o: {
                        answers?: (string | undefined)[];
                        startTimeoutMs?: number;
                        setState?: { file: string; patch: Partial<StoredRunState> };
                    }) => {
                        this.hooks = {
                            answers: [...(o?.answers ?? [])], messages: [], log: [],
                        };
                        if (o?.startTimeoutMs) this.startTimeoutMs = o.startTimeoutMs;
                        if (o?.setState) await this.saveState(o.setState.file, o.setState.patch);
                    }),
                vscode.commands.registerCommand('gelb.internal.runStatus',
                    (file?: string) => this.statusForTests(file)));
        }
        this.adoptRunning();
        return subs;
    }
}

/* ------------------------------------------------------------------ */
/*  CodeLens                                                          */
/* ------------------------------------------------------------------ */

class RunCodeLensProvider implements vscode.CodeLensProvider {
    provideCodeLenses(doc: vscode.TextDocument): vscode.CodeLens[] {
        const line = runLensLine(doc.getText());
        const range = new vscode.Range(line, 0, line, 0);
        return [
            new vscode.CodeLens(range, {
                command: 'gelb.run', title: '▶ Run',
                tooltip: 'Run this file with gelb-run (parameters in the '
                    + 'GeLB sidebar\'s Run view)',
                arguments: [doc.uri],
            }),
            new vscode.CodeLens(range, {
                command: 'gelb.showRunView', title: 'Run with...',
                tooltip: 'Show the Run view to set time steps, constants, '
                    + 'backend and output folder',
                arguments: [doc.uri],
            }),
        ];
    }
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function isCount(v: unknown, min: number): v is number {
    return typeof v === 'number' && Number.isInteger(v) && v >= min;
}

function mtimeOf(p: string): number | undefined {
    try {
        return fs.statSync(p).mtimeMs;
    } catch {
        return undefined;
    }
}

function errorText(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
}

/** How a run that was not stopped ended, after "run #3 (x.gelb) ". */
function describeEnd(exitCode: number | undefined, pid: number | undefined): string {
    if (exitCode === undefined) {
        return pid === undefined
            ? 'did not start: VS Code launched no process (see its terminal); press Run again'
            : 'ended without an exit status: its terminal was closed, or it was killed';
    }
    switch (exitCode) {
        case 130: return 'was interrupted (exit status 130)';
        case 126: return 'failed: gelb-run is not executable (exit status 126)';
        case 127: return 'failed: a command was not found (exit status 127)';
        default: return `failed: gelb-run exited with status ${exitCode}`;
    }
}

function timestamp(): string {
    const d = new Date();
    const p = (n: number, w = 2) => String(n).padStart(w, '0');
    return `[${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}]`;
}

function isExecutableFile(p: string): boolean {
    try {
        fs.accessSync(p, fs.constants.X_OK);
        return fs.statSync(p).isFile();
    } catch {
        return false;
    }
}

/** An input-box message when `arg` cannot go on the shell line. */
function quotingProblem(arg: string): string | undefined {
    try {
        quoteForPosixShell(arg);
        return undefined;
    } catch (e: any) {
        return e instanceof UnquotableError
            ? `Not allowed: ${e.message.replace(/^.*?: /, '')}` : String(e);
    }
}

function describeHome(p: string): string {
    const home = os.homedir();
    return p === home || p.startsWith(home + path.sep)
        ? '~' + p.slice(home.length) : p;
}

function describeFolder(folder: string, file: string): string {
    return path.resolve(folder) === path.dirname(file)
        ? 'next to the source file' : describeHome(folder);
}

/**
 * Integer input with an error (blocks acceptance) and an optional
 * warning (does not): `showInputBox` cannot accept with a message
 * shown on VS Code 1.74, a `createInputBox` can. Resolves to the
 * number, to `null` for an accepted empty value (with `allowEmpty`),
 * or to undefined when cancelled.
 */
function askInteger(o: {
    title: string;
    prompt?: string;
    value?: number;
    min: number;
    allowEmpty?: boolean;
    warn?: (n: number) => string | undefined;
}): Promise<number | null | undefined> {
    return new Promise((resolve) => {
        const box = vscode.window.createInputBox();
        box.title = o.title;
        box.prompt = o.prompt
            ?? `An integer, at least ${o.min}. Enter to accept, Escape to cancel.`;
        box.value = o.value === undefined ? '' : String(o.value);
        const severity = (vscode as any).InputBoxValidationSeverity;
        const check = (text: string): { error?: string; warning?: string } => {
            const t = text.trim();
            if (!t) return o.allowEmpty ? {} : { error: 'Enter a number.' };
            if (!/^\d+$/.test(t) || Number(t) < o.min) {
                return { error: `Expected an integer >= ${o.min}.` };
            }
            if (!Number.isSafeInteger(Number(t))) return { error: 'Too large.' };
            return { warning: o.warn?.(Number(t)) };
        };
        const show = (text: string) => {
            const r = check(text);
            if (r.error) {
                box.validationMessage = severity
                    ? { message: r.error, severity: severity.Error } : r.error;
            } else if (r.warning) {
                box.validationMessage = severity
                    ? { message: r.warning, severity: severity.Warning } : r.warning;
            } else {
                box.validationMessage = undefined;
            }
        };
        let done = false;
        box.onDidChangeValue(show);
        box.onDidAccept(() => {
            const t = box.value.trim();
            if (check(t).error) return;
            done = true;
            resolve(t ? Number(t) : null);
            box.hide();
        });
        box.onDidHide(() => {
            if (!done) resolve(undefined);
            box.dispose();
        });
        show(box.value);
        box.show();
    });
}
