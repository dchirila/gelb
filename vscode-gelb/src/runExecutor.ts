/**
 * Runs gelb-run as a VS Code task the extension owns: the RunExecutor
 * of runController.ts. Nothing is typed into a terminal; VS Code starts
 * the process in its task terminal ("GeLB run: <file> #<id>"), reusing
 * an idle one, and reports its start and end.
 *
 * Environment:
 *   - a gelb-run found as an absolute path (source checkout, GeLB
 *     installation, the PATH, or a path in `gelb.gelbRunCommand`) runs
 *     as a ProcessExecution: no shell, the arguments as a vector, the
 *     output folder as the working directory. It gets VS Code's own
 *     environment (resolved from the login shell when VS Code starts)
 *     and `terminal.integrated.env.<os>`;
 *   - a bare `gelb-run` that only a shell can find (gelbTools.ts, step
 *     5, or a bare name in the setting) runs as a ShellExecution of the
 *     same task: `cd '<folder>' && 'gelb-run' ...` in VS Code's task
 *     shell, whose PATH has the same sources plus what that shell reads
 *     when it starts (~/.zshenv). Exit status 127 then means that shell
 *     did not find gelb-run.
 *
 * In a window without a folder VS Code refuses to start a new task
 * terminal anywhere but in the home folder (the first launch fails
 * without a process), so the task starts there and changes into the
 * output folder itself.
 *
 * Each request gets its own task definition (`request`): VS Code hands
 * back the running execution when a task with the same definition is
 * executed again, and the definition is what ties an event to its run.
 */

import * as vscode from 'vscode';
import * as os from 'os';

import { RunExecution, RunExecutor, RunListener } from './runController';

/** The task type, contributed in package.json (taskDefinitions). */
export const TASK_TYPE = 'gelb-run';

/** Everything one run needs, fixed when the request was accepted. */
export interface RunSpec {
    /** The .gelb file. */
    file: string;
    /** The working directory, where the .nc lands. */
    folder: string;
    /** gelb-run: an absolute path, or a bare name for the shell. */
    runner: string;
    /** Where the runner was found, for the log. */
    runnerFrom: string;
    /** Run through VS Code's task shell (bare runner name). */
    viaShell: boolean;
    /** The arguments after the runner. */
    args: string[];
    /** The equivalent shell line, `cd ... && gelb-run ...`: what the
     *  shell runs when `viaShell`, and what the log shows. */
    commandLine: string;
    /** The backend, for the log. */
    backend: string;
    /** The .nc the run writes, and its modification time before. */
    output: string;
    outputMtimeBefore?: number;
}

interface Entry {
    listener: RunListener;
    pid?: number;
    ended: boolean;
}

export class TaskRunExecutor implements RunExecutor<RunSpec>, vscode.Disposable {
    /** Distinguishes this window's requests from earlier sessions'. */
    private readonly session = `${process.pid.toString(36)}.${Date.now().toString(36)}`;
    private readonly entries = new Map<string, Entry>();
    private readonly subs: vscode.Disposable[];

    constructor() {
        this.subs = [
            vscode.tasks.onDidStartTaskProcess((e) => {
                const entry = this.entryOf(e.execution);
                if (!entry || entry.ended) return;
                entry.pid = e.processId;
                entry.listener.started(e.processId);
            }),
            vscode.tasks.onDidEndTaskProcess((e) => this.end(e.execution, e.exitCode)),
            // A task can end without a process end (it never launched one).
            vscode.tasks.onDidEndTask((e) => this.end(e.execution, undefined)),
        ];
    }

    /** The name of request `id`'s task, which is also its terminal's. */
    static taskName(file: string, id: number): string {
        return `GeLB run: ${baseName(file)} #${id}`;
    }

    async launch(id: number, spec: RunSpec, listener: RunListener): Promise<RunExecution> {
        const request = `${this.session}-${id}`;
        const entry: Entry = { listener, ended: false };
        this.entries.set(request, entry);
        let execution: vscode.TaskExecution;
        try {
            execution = await vscode.tasks.executeTask(this.task(id, request, spec));
        } catch (e) {
            this.entries.delete(request);
            throw e;
        }
        return {
            interrupt: () => interruptGroup(entry.pid),
            terminate: () => execution.terminate(),
        };
    }

    /** GeLB run tasks still going, e.g. from before a window reload. */
    ownExecutions(): vscode.TaskExecution[] {
        return vscode.tasks.taskExecutions.filter(
            e => e.task.definition.type === TASK_TYPE);
    }

    /** Follow an execution found by ownExecutions(). Its process id is
     *  unknown, so Stop terminates it rather than sending Ctrl-C. */
    attach(execution: vscode.TaskExecution, listener: RunListener): RunExecution {
        const request = requestOf(execution) ?? `adopted-${Date.now()}`;
        this.entries.set(request, { listener, ended: false });
        return {
            interrupt: () => false,
            terminate: () => execution.terminate(),
        };
    }

    dispose(): void {
        for (const s of this.subs) s.dispose();
        this.entries.clear();
    }

    private entryOf(execution: vscode.TaskExecution): Entry | undefined {
        const request = requestOf(execution);
        return request === undefined ? undefined : this.entries.get(request);
    }

    private end(execution: vscode.TaskExecution, exitCode: number | undefined): void {
        const request = requestOf(execution);
        const entry = request === undefined ? undefined : this.entries.get(request);
        if (!entry || entry.ended) return;
        entry.ended = true;
        this.entries.delete(request!);
        entry.listener.ended(exitCode);
    }

    private task(id: number, request: string, spec: RunSpec): vscode.Task {
        const folderless = !(vscode.workspace.workspaceFolders?.length);
        const cwd = folderless ? os.homedir() : spec.folder;
        let execution: vscode.ProcessExecution | vscode.ShellExecution;
        if (spec.viaShell) {
            // The line begins with its own cd, so neither the home-folder
            // start nor the shell's startup files decide the folder.
            execution = new vscode.ShellExecution(spec.commandLine, { cwd });
        } else if (folderless && process.platform !== 'win32') {
            execution = new vscode.ProcessExecution('/bin/sh',
                ['-c', 'cd -- "$1" && shift && exec "$@"', 'gelb-run',
                    spec.folder, spec.runner, ...spec.args],
                { cwd });
        } else {
            execution = new vscode.ProcessExecution(spec.runner, spec.args, { cwd });
        }
        const scope = vscode.workspace.getWorkspaceFolder(vscode.Uri.file(spec.file))
            ?? vscode.TaskScope.Workspace;
        const task = new vscode.Task(
            { type: TASK_TYPE, request, file: spec.file },
            scope, TaskRunExecutor.taskName(spec.file, id), 'GeLB', execution, []);
        task.presentationOptions = {
            reveal: vscode.TaskRevealKind.Always,
            focus: false,
            echo: true,
            panel: vscode.TaskPanelKind.Shared,
            clear: true,
            showReuseMessage: false,
        };
        return task;
    }
}

function requestOf(execution: vscode.TaskExecution): string | undefined {
    const d = execution.task.definition;
    return d.type === TASK_TYPE && typeof d.request === 'string' ? d.request : undefined;
}

/**
 * Ctrl-C for a task: SIGINT to its process group, which is the task
 * process's own (VS Code starts it as a session leader), so gelb-run,
 * its compiler, the simulation and the viewer all receive it, as they
 * would from Ctrl-C in a terminal. gelb-run's trap then stops the
 * simulation and removes its temporary files.
 */
function interruptGroup(pid: number | undefined): boolean {
    if (!pid || process.platform === 'win32') return false;
    try {
        process.kill(-pid, 'SIGINT');
        return true;
    } catch {
        try {
            process.kill(pid, 'SIGINT');
            return true;
        } catch {
            return false;
        }
    }
}

function baseName(file: string): string {
    return file.replace(/^.*[\\/]/, '');
}
