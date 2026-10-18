/**
 * The Run view's request lifecycle, apart from VS Code: one run at a
 * time, from the click to the end of its process, each with its own
 * request id, and Stop cancelling whatever stage that run is in.
 *
 * The execution itself (a VS Code task, see runExecutor.ts) and the
 * user interface are adapters passed in, so mocha can drive this module
 * with fakes (test/runController.test.js). No `vscode` import here.
 *
 * States, as the view shows them:
 *
 *   idle      nothing going; the last run (if any) ended well or was stopped
 *   starting  a request is being prepared (file saved, gelb-run found) or
 *             its task is launched and has not reported its process yet
 *   running   the process has started (compiling, simulating, or waiting
 *             for its viewer window)
 *   stopping  Stop was pressed; waiting for the process to end
 *   failed    the last run failed, or its start or stop was never
 *             confirmed (the execution may still be alive then, and Run
 *             asks before starting another)
 *
 * Rules: a click on Run while a request is starting is ignored
 * (coalesced) and said so; while one is running or unconfirmed, Run
 * asks whether to stop it first. Nothing is ever retried automatically.
 */

export type RunState = 'idle' | 'starting' | 'running' | 'stopping' | 'failed';

/** Where one request is. `unconfirmed`: launched, but neither its start
 *  (in time) nor its stop was ever confirmed. */
export type RunPhase =
    | 'preparing' | 'launching' | 'starting' | 'running'
    | 'unconfirmed' | 'stopping' | 'ended';

/** What the executor reports about one launched process. */
export interface RunListener {
    /** The process started; `pid` undefined when the host launched no
     *  process after all (its end follows). */
    started(pid: number | undefined): void;
    /** The process ended; `exitCode` undefined when it was killed, or
     *  never launched. */
    ended(exitCode: number | undefined): void;
}

/** A launched execution. */
export interface RunExecution {
    /** Ctrl-C: SIGINT to the process group. False when that cannot be
     *  done (no process id yet, Windows); terminate() then. */
    interrupt(): boolean;
    /** End it for good (VS Code ends the task's terminal process). */
    terminate(): void;
}

/** Launches the process of one request. Rejects when nothing could be
 *  launched at all. */
export interface RunExecutor<S> {
    launch(id: number, spec: S, listener: RunListener): Promise<RunExecution>;
}

export interface RunRequest<S> {
    readonly id: number;
    /** What the request runs, for messages (the file's name). */
    readonly label: string;
    phase: RunPhase;
    /** Snapshot taken when the request was prepared. */
    spec?: S;
    execution?: RunExecution;
    pid?: number;
    exitCode?: number;
    /** Stop came before the launch was done. */
    cancelled: boolean;
    /** Stop was pressed for it (or for it to make way for another). */
    stopRequested: boolean;
    /** Why it failed, for the view. */
    failure?: string;
}

/** The user interface, as far as the lifecycle needs one. */
export interface RunUi<S> {
    log(id: number | undefined, text: string): void;
    /** The state or the current request changed. */
    changed(state: RunState, request: RunRequest<S> | undefined): void;
    /** Run was clicked while `current` is going: stop it and run
     *  `next` instead? */
    confirmStopAndRun(current: RunRequest<S>, next: string): Promise<boolean>;
    /** A click on Run was ignored because `current` is starting or
     *  stopping (or a question about it is open). */
    coalesced(current: RunRequest<S> | undefined, next: string): void;
    /** `req` was launched but has not reported its start in time. */
    unconfirmed(req: RunRequest<S>, afterMs: number): void;
    /** `req` ended on its own (not stopped): exit code 0 or not, or
     *  undefined for a process that was killed or never launched. */
    ended(req: RunRequest<S>): void;
    /** The launch itself failed (the executor rejected). */
    launchFailed(req: RunRequest<S>, error: unknown): void;
    /** Preparing `req` failed (the error says why, for the user). */
    prepareFailed(req: RunRequest<S>, error: unknown): void;
    /** Stop did not end `req` in time. */
    stopUnconfirmed(req: RunRequest<S>, afterMs: number): void;
    /** Stop with nothing to stop. */
    nothingToStop(): void;
}

export interface RunTimeouts {
    /** How long a launched task may take to report its process. */
    startMs: number;
    /** After Stop's Ctrl-C, how long before the task is terminated. */
    interruptGraceMs: number;
    /** After that, how long before the stop is reported unconfirmed. */
    stopMs: number;
}

export const DEFAULT_TIMEOUTS: RunTimeouts = {
    startMs: 10000,
    interruptGraceMs: 3000,
    stopMs: 5000,
};

/**
 * `prepare` turns the click into a snapshot of everything the run needs
 * (the saved file, its parameters, the runner), or undefined when there
 * is nothing to run (it has told the user why), or throws an error the
 * view shows. It is called once per accepted request and may take its
 * time: Stop meanwhile cancels the request.
 */
export type Prepare<S> = (req: RunRequest<S>) => Promise<S | undefined>;

export class RunController<S> {
    private nextId = 1;
    private current: RunRequest<S> | undefined;
    /** The last request that ended (for the failed state). */
    private last: RunRequest<S> | undefined;
    /** A Stop-and-Run question is open, or its stop is under way. */
    private switching = false;
    /** Bumped by every Stop: a Stop-and-Run that started before it
     *  does not launch anything after it. */
    private stopCount = 0;
    private readonly endWaiters = new Map<RunRequest<S>, Array<(ended: boolean) => void>>();
    private readonly timers = new Map<RunRequest<S>, ReturnType<typeof setTimeout>[]>();

    constructor(
        private readonly executor: RunExecutor<S>,
        private readonly ui: RunUi<S>,
        public timeouts: RunTimeouts = { ...DEFAULT_TIMEOUTS },
    ) {}

    get state(): RunState {
        const r = this.current;
        if (!r) return this.last?.failure ? 'failed' : 'idle';
        switch (r.phase) {
            case 'preparing':
            case 'launching':
            case 'starting':
                return 'starting';
            case 'running':
                return 'running';
            case 'stopping':
                return 'stopping';
            default:
                return 'failed';
        }
    }

    /** The request that owns (or is about to own) an execution. */
    get request(): RunRequest<S> | undefined {
        return this.current;
    }

    /** The request the view describes: the current one, else the last. */
    get shown(): RunRequest<S> | undefined {
        return this.current ?? this.last;
    }

    /** True while an execution may be alive: Stop has something to do. */
    get busy(): boolean {
        return this.current !== undefined;
    }

    /**
     * A click on Run for `label`. Resolves once the request is launched,
     * refused or cancelled; not when the run ends.
     */
    async run(label: string, prepare: Prepare<S>): Promise<void> {
        const cur = this.current;
        if (this.switching || (cur && cur.phase !== 'running' && cur.phase !== 'unconfirmed')) {
            this.ui.log(cur?.id, `Run of ${label} ignored: `
                + (this.switching ? 'a question about the current run is open'
                    : `run #${cur!.id} is still ${cur!.phase}`));
            this.ui.coalesced(cur, label);
            return;
        }
        if (cur) {
            if (!(await this.stopFirst(cur, label))) return;
        }

        const req: RunRequest<S> = {
            id: this.nextId++, label, phase: 'preparing',
            cancelled: false, stopRequested: false,
        };
        this.current = req;
        this.ui.log(req.id, `Run requested: ${label}`);
        this.changed();

        let spec: S | undefined;
        try {
            spec = await prepare(req);
        } catch (e) {
            if (req.cancelled) return;
            this.finish(req, `not started: ${errorText(e)}`);
            this.ui.prepareFailed(req, e);
            return;
        }
        if (req.cancelled) return;          // Stop has said so already
        if (spec === undefined) {
            this.ui.log(req.id, 'not started');
            this.finish(req, undefined);
            return;
        }

        req.spec = spec;
        req.phase = 'launching';
        this.changed();
        this.arm(req, this.timeouts.startMs, () => this.startTimedOut(req));
        let execution: RunExecution;
        try {
            execution = await this.executor.launch(req.id, spec, this.listener(req));
        } catch (e) {
            if (phaseOf(req) === 'ended') return;
            if (req.cancelled) {
                this.ui.log(req.id, `launch failed after Stop: ${errorText(e)}`);
                this.finish(req, undefined);
                return;
            }
            this.finish(req, `could not be launched: ${errorText(e)}`);
            this.ui.launchFailed(req, e);
            return;
        }
        req.execution = execution;
        if (req.cancelled) {
            // Stop came while the task was being created: end it now,
            // even when the request was given up on meanwhile.
            this.ui.log(req.id, 'launched after Stop; terminating it');
            execution.terminate();
            return;
        }
        if (phaseOf(req) === 'ended') return;   // it ran and ended already
        if (phaseOf(req) === 'launching') {
            req.phase = 'starting';
            this.changed();
        }
    }

    /** Stop: cancel the request in whatever stage it is. */
    async stop(): Promise<void> {
        this.stopCount++;
        const req = this.current;
        if (!req) {
            this.ui.nothingToStop();
            return;
        }
        switch (req.phase) {
            case 'preparing':
                req.cancelled = true;
                req.stopRequested = true;
                this.ui.log(req.id, 'cancelled before launch');
                this.finish(req, undefined);
                return;
            case 'launching':
                // run() terminates the execution once the launch returns.
                req.cancelled = true;
                req.stopRequested = true;
                req.phase = 'stopping';
                this.ui.log(req.id, 'Stop while launching: cancelled');
                this.changed();
                this.armStopTimeout(req, 0);
                return;
            case 'stopping':
                // A second Stop does not wait for Ctrl-C.
                this.ui.log(req.id, 'Stop again: terminating the task');
                req.execution?.terminate();
                return;
            default:
                await this.stopExecution(req);
        }
    }

    /**
     * Take over an execution that is already going: one found by its
     * task after a window reload. It is running as far as the view can
     * tell; Stop ends it.
     */
    adopt(label: string, attach: (listener: RunListener) => RunExecution): RunRequest<S> {
        const req: RunRequest<S> = {
            id: this.nextId++, label, phase: 'running',
            cancelled: false, stopRequested: false,
        };
        req.execution = attach(this.listener(req));
        if (req.phase === 'running') {
            this.current = req;
            this.changed();
        }
        return req;
    }

    /**
     * Record a run that ended unseen: one that was going when the window
     * was reloaded or closed and that VS Code ended with it. It becomes
     * the last request, failed, so the view says what became of it.
     */
    noteLost(id: number, label: string, failure: string): void {
        if (this.current) return;
        this.last = {
            id, label, phase: 'ended', cancelled: false, stopRequested: false, failure,
        };
        this.ui.log(id, `${label}: ${failure}`);
        this.changed();
    }

    dispose(): void {
        for (const ts of this.timers.values()) ts.forEach(clearTimeout);
        this.timers.clear();
    }

    /* ---------- internals */

    /** Ask, then stop `cur`; true when the new run may go ahead. */
    private async stopFirst(cur: RunRequest<S>, label: string): Promise<boolean> {
        const stops = this.stopCount;
        this.switching = true;
        try {
            const yes = await this.ui.confirmStopAndRun(cur, label);
            if (!yes || stops !== this.stopCount) return false;
            if (this.current === cur && cur.phase !== 'ended') {
                this.ui.log(cur.id, `stopping it to run ${label}`);
                const ended = await this.stopExecution(cur);
                if (!ended || stops !== this.stopCount) return false;
            }
            return this.current === undefined;
        } finally {
            this.switching = false;
        }
    }

    /** Ctrl-C, then terminate after the grace period; resolves true
     *  when the process has ended, false when that was not confirmed. */
    private stopExecution(req: RunRequest<S>): Promise<boolean> {
        const done = this.waitForEnd(req);
        const execution = req.execution;
        req.stopRequested = true;
        this.clearTimers(req);
        if (!execution) {
            // Its launch never returned (start unconfirmed): give it up.
            // Should the launch return after all, run() terminates it.
            req.cancelled = true;
            this.ui.log(req.id, 'Stop: the launch never returned; given up '
                + '(terminated should it still return)');
            this.finish(req, undefined);
            return done;
        }
        req.phase = 'stopping';
        this.changed();
        if (execution.interrupt()) {
            this.ui.log(req.id, 'Stop: Ctrl-C (SIGINT) sent to the run\'s processes');
            this.arm(req, this.timeouts.interruptGraceMs, () => {
                this.ui.log(req.id, `still going after ${seconds(this.timeouts.interruptGraceMs)}; `
                    + 'terminating the task');
                execution.terminate();
            });
            this.armStopTimeout(req, this.timeouts.interruptGraceMs);
        } else {
            this.ui.log(req.id, 'Stop: terminating the task');
            execution.terminate();
            this.armStopTimeout(req, 0);
        }
        return done;
    }

    private armStopTimeout(req: RunRequest<S>, after: number): void {
        const ms = after + this.timeouts.stopMs;
        this.arm(req, ms, () => {
            if (req.phase !== 'stopping') return;
            req.phase = 'unconfirmed';
            req.failure = `did not confirm its stop within ${seconds(ms)}`;
            this.ui.log(req.id, req.failure);
            this.changed();
            this.resolveEnd(req, false);
            this.ui.stopUnconfirmed(req, ms);
        });
    }

    private startTimedOut(req: RunRequest<S>): void {
        if (req.phase !== 'launching' && req.phase !== 'starting') return;
        req.phase = 'unconfirmed';
        req.failure = `start not confirmed after ${seconds(this.timeouts.startMs)}`;
        this.ui.log(req.id, `${req.failure}; it may still start (Stop cancels it)`);
        this.changed();
        this.ui.unconfirmed(req, this.timeouts.startMs);
    }

    private listener(req: RunRequest<S>): RunListener {
        return {
            started: (pid) => {
                if (req.phase === 'ended') return;
                if (pid === undefined) {
                    this.ui.log(req.id, 'the task reported a start without a process');
                    return;
                }
                req.pid = pid;
                if (req.phase === 'stopping') {
                    this.ui.log(req.id, `process ${pid} started after Stop`);
                    return;
                }
                const late = req.phase === 'unconfirmed';
                req.phase = 'running';
                req.failure = undefined;
                this.clearTimers(req);
                this.ui.log(req.id, `running (pid ${pid})${late ? ', later than expected' : ''}`);
                if (this.current === req) this.changed();
            },
            ended: (exitCode) => {
                if (req.phase === 'ended') return;
                const stopped = req.stopRequested;
                req.exitCode = exitCode;
                const status = exitCode === undefined ? 'no exit status' : `exit status ${exitCode}`;
                if (stopped) {
                    this.ui.log(req.id, `stopped (${status})`);
                    this.finish(req, undefined);
                    return;
                }
                const failure = exitCode === 0 ? undefined
                    : req.pid === undefined && exitCode === undefined
                        ? 'did not start: no process was launched'
                        : `failed: ${status}`;
                this.ui.log(req.id, failure ? `ended: ${failure}` : `ended (${status})`);
                this.finish(req, failure);
                this.ui.ended(req);
            },
        };
    }

    /** `req` is over: record why (undefined: fine or stopped). */
    private finish(req: RunRequest<S>, failure: string | undefined): void {
        req.phase = 'ended';
        req.failure = failure;
        this.clearTimers(req);
        if (this.current === req) {
            this.current = undefined;
            this.last = req;
            this.changed();
        }
        this.resolveEnd(req, true);
    }

    private waitForEnd(req: RunRequest<S>): Promise<boolean> {
        if (req.phase === 'ended') return Promise.resolve(true);
        return new Promise((resolve) => {
            const list = this.endWaiters.get(req) ?? [];
            list.push(resolve);
            this.endWaiters.set(req, list);
        });
    }

    private resolveEnd(req: RunRequest<S>, ended: boolean): void {
        const list = this.endWaiters.get(req);
        this.endWaiters.delete(req);
        for (const r of list ?? []) r(ended);
    }

    private arm(req: RunRequest<S>, ms: number, fn: () => void): void {
        const t = setTimeout(fn, ms);
        const list = this.timers.get(req) ?? [];
        list.push(t);
        this.timers.set(req, list);
    }

    private clearTimers(req: RunRequest<S>): void {
        for (const t of this.timers.get(req) ?? []) clearTimeout(t);
        this.timers.delete(req);
    }

    private changed(): void {
        this.ui.changed(this.state, this.current);
    }
}

/** The phase as it is now: events change it during an await, which
 *  TypeScript's narrowing does not know. */
function phaseOf(req: RunRequest<unknown>): RunPhase {
    return req.phase;
}

function errorText(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
}

function seconds(ms: number): string {
    return `${Math.round(ms / 100) / 10} s`;
}
