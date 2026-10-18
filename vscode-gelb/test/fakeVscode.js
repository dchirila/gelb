/**
 * A fake `vscode` module for driving the Run view (out/runView.js)
 * without VS Code: just enough of the window, workspace, commands and
 * tasks API for RunProvider, plus a `world` that the tests control and
 * inspect: what was launched (a line typed into a terminal, or a task
 * executed), which messages were shown, the context keys, and when a
 * launched process starts and ends.
 *
 * install() makes `require('vscode')` return this module; reset() gives
 * every test a fresh world. Nothing here starts a process: a "launch"
 * is a record, and its start and end are events the test fires.
 */

const Module = require('module');
const path = require('path');

/* ------------------------------------------------------------------ */
/*  Small API classes                                                 */
/* ------------------------------------------------------------------ */

class Disposable {
    constructor(fn) { this.fn = fn; }
    dispose() { if (this.fn) this.fn(); this.fn = undefined; }
}

class EventEmitter {
    constructor() {
        this.listeners = [];
        this.event = (fn) => {
            this.listeners.push(fn);
            return new Disposable(() => {
                this.listeners = this.listeners.filter(l => l !== fn);
            });
        };
    }
    fire(e) { for (const l of [...this.listeners]) l(e); }
    dispose() { this.listeners = []; }
}

class Uri {
    constructor(fsPath) {
        this.scheme = 'file';
        this.fsPath = fsPath;
        this.path = fsPath;
    }
    static file(p) { return new Uri(path.resolve(p)); }
    toString() { return `file://${this.fsPath}`; }
}

class ThemeIcon {
    constructor(id) { this.id = id; }
}
ThemeIcon.File = new ThemeIcon('file');

class TreeItem {
    constructor(label, collapsibleState) {
        this.label = label;
        this.collapsibleState = collapsibleState;
    }
}

class Range {
    constructor(a, b, c, d) { Object.assign(this, { a, b, c, d }); }
}

class CodeLens {
    constructor(range, command) { this.range = range; this.command = command; }
}

class ProcessExecution {
    constructor(process, args, options) {
        this.process = process;
        this.args = args ?? [];
        this.options = options;
    }
}

class ShellExecution {
    constructor(commandLine, options) {
        this.commandLine = commandLine;
        this.options = options;
    }
}

class Task {
    constructor(definition, scope, name, source, execution, problemMatchers) {
        Object.assign(this, { definition, scope, name, source, execution, problemMatchers });
    }
}

/* ------------------------------------------------------------------ */
/*  The world                                                         */
/* ------------------------------------------------------------------ */

let nextPid = 2000000;

function newWorld() {
    const w = {
        config: {},                 // 'gelb.gelbRunCommand' → value
        contexts: {},               // setContext key → value
        messages: [],               // { level, message, options, items }
        statusBar: [],              // setStatusBarMessage texts
        output: [],                 // output channel lines
        launches: [],               // see recordLaunch()
        terminals: [],
        workspaceFolders: undefined,
        documents: [],
        activeEditor: undefined,
        /** Launched processes report their start at once. */
        autoStart: true,
        /** How a message is answered: (level, message, items) → item. */
        answer: () => undefined,
        signals: [],                // process.kill calls intercepted
        emitters: {
            closeTerminal: new EventEmitter(),
            shellStart: new EventEmitter(),
            shellEnd: new EventEmitter(),
            taskProcStart: new EventEmitter(),
            taskProcEnd: new EventEmitter(),
            taskEnd: new EventEmitter(),
            config: new EventEmitter(),
        },
    };

    w.recordLaunch = (launch) => {
        launch.index = w.launches.length;
        launch.started = false;
        launch.ended = false;
        launch.stopped = false;
        w.launches.push(launch);
        return launch;
    };

    /** The process of `launch` starts (shell integration or the task
     *  system reports it). */
    w.start = (launch) => {
        if (launch.started || launch.ended) return;
        launch.started = true;
        if (launch.kind === 'terminal') {
            // gelb-run removes its start marker first thing.
            const marker = launch.terminal.creationOptions.env?.GELB_RUN_STARTED;
            if (marker) require('fs').rmSync(marker, { force: true });
            w.emitters.shellStart.fire({ terminal: launch.terminal });
        } else {
            launch.pid = nextPid++;
            w.emitters.taskProcStart.fire({ execution: launch.execution, processId: launch.pid });
        }
    };

    /** The process of `launch` ends with `exitCode`. */
    w.finish = (launch, exitCode) => {
        if (launch.ended) return;
        launch.ended = true;
        if (launch.kind === 'terminal') {
            w.emitters.shellEnd.fire({ terminal: launch.terminal, exitCode });
        } else {
            w.emitters.taskProcEnd.fire({ execution: launch.execution, exitCode });
            w.emitters.taskEnd.fire({ execution: launch.execution });
        }
    };

    /** Something else ends: a command typed in a terminal, another
     *  extension's task. Neither is a GeLB run. */
    w.fireUnrelatedEnd = () => {
        for (const t of w.terminals) w.emitters.shellEnd.fire({ terminal: t, exitCode: 0 });
        const other = { task: new Task({ type: 'shell' }, 2, 'build', 'Workspace') };
        w.emitters.taskProcEnd.fire({ execution: other, exitCode: 0 });
        w.emitters.taskEnd.fire({ execution: other });
    };

    /** Something else starts in the same terminals or task system. */
    w.fireUnrelatedStart = () => {
        for (const t of w.terminals) w.emitters.shellStart.fire({ terminal: t });
        const other = { task: new Task({ type: 'shell' }, 2, 'build', 'Workspace') };
        w.emitters.taskProcStart.fire({ execution: other, processId: 1 });
    };

    w.active = () => w.launches.filter(l => !l.ended);
    return w;
}

let world = newWorld();

function message(level) {
    return (msg, ...rest) => {
        let options;
        if (rest.length && typeof rest[0] === 'object' && rest[0] !== null
            && !('title' in rest[0])) {
            options = rest.shift();
        }
        const items = rest;
        world.messages.push({ level, message: msg, options, items });
        return Promise.resolve(world.answer(level, msg, items, options));
    };
}

function makeTerminal(options) {
    const t = {
        name: options.name,
        creationOptions: options,
        processId: Promise.resolve(nextPid++),
        exitStatus: undefined,
        shown: 0,
        typed: [],
        show() { this.shown++; },
        sendText(text, addNewLine = true) {
            this.typed.push(text);
            if (text === '\u0003') {
                for (const l of world.active()) {
                    if (l.terminal === this) {
                        l.stopped = true;
                        world.finish(l, 130);
                    }
                }
                return;
            }
            if (!addNewLine) return;
            const l = world.recordLaunch({ kind: 'terminal', terminal: this, line: text });
            if (world.autoStart) world.start(l);
        },
        dispose() {
            this.exitStatus = { code: undefined };
            world.terminals = world.terminals.filter(x => x !== this);
            world.emitters.closeTerminal.fire(this);
        },
    };
    world.terminals.push(t);
    return t;
}

const vscode = {
    Disposable, EventEmitter, Uri, ThemeIcon, TreeItem, Range, CodeLens,
    ProcessExecution, ShellExecution, Task,
    TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
    QuickPickItemKind: { Separator: -1, Default: 0 },
    TaskScope: { Global: 1, Workspace: 2 },
    TaskRevealKind: { Always: 1, Silent: 2, Never: 3 },
    TaskPanelKind: { Shared: 1, Dedicated: 2, New: 3 },
    ExtensionMode: { Production: 1, Development: 2, Test: 3 },
    StatusBarAlignment: { Left: 1, Right: 2 },

    window: {
        get activeTextEditor() { return world.activeEditor; },
        get terminals() { return world.terminals; },
        showErrorMessage: message('error'),
        showWarningMessage: message('warning'),
        showInformationMessage: message('info'),
        setStatusBarMessage: (text) => {
            world.statusBar.push(text);
            return new Disposable();
        },
        createTerminal: (options) => makeTerminal(options),
        createOutputChannel: (name) => ({
            name,
            appendLine: (s) => world.output.push(s),
            append: (s) => world.output.push(s),
            show: () => undefined,
            clear: () => undefined,
            dispose: () => undefined,
        }),
        registerTreeDataProvider: () => new Disposable(),
        onDidCloseTerminal: (fn) => world.emitters.closeTerminal.event(fn),
        onDidStartTerminalShellExecution: (fn) => world.emitters.shellStart.event(fn),
        onDidEndTerminalShellExecution: (fn) => world.emitters.shellEnd.event(fn),
        showQuickPick: () => Promise.resolve(undefined),
        showInputBox: () => Promise.resolve(undefined),
        showOpenDialog: () => Promise.resolve(undefined),
    },

    workspace: {
        get workspaceFolders() { return world.workspaceFolders; },
        get textDocuments() { return world.documents; },
        getConfiguration: (section) => ({
            get: (key, dflt) => {
                const v = world.config[`${section}.${key}`];
                return v === undefined ? dflt : v;
            },
        }),
        getWorkspaceFolder: (uri) => (world.workspaceFolders ?? []).find(
            f => uri.fsPath === f.uri.fsPath || uri.fsPath.startsWith(f.uri.fsPath + path.sep)),
        openTextDocument: (uri) => Promise.resolve(
            world.documents.find(d => d.uri.toString() === uri.toString())),
        onDidChangeConfiguration: (fn) => world.emitters.config.event(fn),
    },

    commands: {
        registered: {},
        registerCommand(id, fn) {
            this.registered[id] = fn;
            return new Disposable(() => delete this.registered[id]);
        },
        executeCommand: (id, ...args) => {
            if (id === 'setContext') world.contexts[args[0]] = args[1];
            return Promise.resolve(undefined);
        },
    },

    languages: {
        registerCodeLensProvider: () => new Disposable(),
    },

    tasks: {
        get taskExecutions() {
            return world.active().filter(l => l.kind === 'task').map(l => l.execution);
        },
        executeTask: (task) => {
            const execution = {
                task,
                terminate() {
                    const l = world.launches.find(x => x.execution === this);
                    if (l) {
                        l.stopped = true;
                        world.finish(l, undefined);
                    }
                },
            };
            const l = world.recordLaunch({ kind: 'task', task, execution });
            if (world.autoStart) setImmediate(() => world.start(l));
            return Promise.resolve(execution);
        },
        onDidStartTaskProcess: (fn) => world.emitters.taskProcStart.event(fn),
        onDidEndTaskProcess: (fn) => world.emitters.taskProcEnd.event(fn),
        onDidEndTask: (fn) => world.emitters.taskEnd.event(fn),
    },
};

/** A .gelb document backed by a file on disk. */
function addDocument(fsPath, text = '') {
    const doc = {
        uri: Uri.file(fsPath),
        languageId: 'gelb',
        isUntitled: false,
        isDirty: false,
        getText: () => text,
        save: () => Promise.resolve(true),
    };
    world.documents.push(doc);
    world.activeEditor = { document: doc };
    return doc;
}

/** An in-memory workspaceState, for the ExtensionContext. */
function fakeContext() {
    const store = new Map();
    return {
        extensionMode: vscode.ExtensionMode.Test,
        subscriptions: [],
        workspaceState: {
            get: (k, d) => (store.has(k) ? store.get(k) : d),
            update: (k, v) => { store.set(k, v); return Promise.resolve(); },
        },
    };
}

/** Route `require('vscode')` to this module. */
function install() {
    const resolve = Module._resolveFilename;
    Module._resolveFilename = function (request, ...rest) {
        if (request === 'vscode') return __filename;
        return resolve.call(this, request, ...rest);
    };
}

/** A fresh world for the next test. Real signals are never sent:
 *  process.kill on a fake process group is recorded instead. */
function reset() {
    world = newWorld();
    vscode.commands.registered = {};
    return world;
}

const realKill = process.kill;
process.kill = function (pid, signal) {
    if (typeof pid === 'number' && Math.abs(pid) >= 2000000) {
        world.signals.push({ pid, signal });
        const l = world.launches.find(x => x.pid === Math.abs(pid));
        if (l && !l.ended && (signal === 'SIGINT' || signal === 'SIGTERM')) {
            l.stopped = true;
            world.finish(l, signal === 'SIGINT' ? 130 : 143);
        }
        return true;
    }
    return realKill.call(process, pid, signal);
};

Object.assign(vscode, { install, reset, addDocument, fakeContext });
Object.defineProperty(vscode, 'world', { get: () => world });
module.exports = vscode;
