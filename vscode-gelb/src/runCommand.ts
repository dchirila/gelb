/**
 * Pure logic behind the sidebar's Run view: gelb-run's arguments and the
 * equivalent shell line, POSIX shell quoting, the tokenizer for the
 * gelbc / gelb-view command settings, and the random() scan that
 * decides whether the seed row is shown.
 *
 * No `vscode` import here, so mocha can test this module from `out/`
 * without starting VS Code (see test/runCommand.test.js).
 */

import * as path from 'path';

import { stripCommentsAndStrings } from './gelbParser';

/* ------------------------------------------------------------------ */
/*  Backends                                                          */
/* ------------------------------------------------------------------ */

export type Backend = 'cpu_fortran_serial' | 'cpu_highway' | 'gpu_cuda_cpp';

/** gelb-run's default backend; `-b` is only emitted for the others. */
export const DEFAULT_BACKEND: Backend = 'cpu_highway';

/** The three backends gelb-run accepts, with a one-line description
 *  for the Run view's quick pick. No probing of the host: a backend
 *  whose toolchain is missing fails in the run's terminal with
 *  gelb-run's own message. */
export const BACKENDS: ReadonlyArray<{ id: Backend; description: string }> = [
    { id: 'cpu_highway',
      description: 'C++ with Google Highway SIMD and OpenMP (default)' },
    { id: 'cpu_fortran_serial',
      description: 'serial Fortran; needs gfortran and NetCDF-Fortran' },
    { id: 'gpu_cuda_cpp',
      description: 'CUDA C++; needs nvcc and an NVIDIA GPU' },
];

export function isBackend(s: unknown): s is Backend {
    return BACKENDS.some(b => b.id === s);
}

/* ------------------------------------------------------------------ */
/*  Run parameters                                                    */
/* ------------------------------------------------------------------ */

export interface RunParams {
    /** `-n`: number of time steps (positive integer). */
    timeSteps: number;
    /** `-w`: write the gauges every N steps (positive integer). */
    writeEvery: number;
    /** `-D NAME=VALUE`, in order; the value is passed verbatim
     *  (gelb-run and gelbc validate it). */
    defines: [string, string][];
    /** `-s`: fixed PRNG seed; undefined = seeded from the clock. */
    seed?: number;
    /** `-b`: omitted from the line when it is the default. */
    backend: Backend;
    /** `--view`: open gelb-view on the output when the run ends. */
    view: boolean;
    /** Working directory of the run, where `<basename>.nc` lands;
     *  undefined = the source file's folder. */
    outputFolder?: string;
}

/* ------------------------------------------------------------------ */
/*  Quoting                                                           */
/* ------------------------------------------------------------------ */

/** Raised for an argument that no single quoting works for in all of
 *  sh, bash, zsh and tcsh. */
export class UnquotableError extends Error {
    constructor(public readonly value: string, reason: string) {
        super(`cannot pass ${JSON.stringify(value)} to the shell: ${reason}`);
        this.name = 'UnquotableError';
    }
}

/**
 * Quote `arg` in single quotes, which keeps spaces, `$`, backquotes,
 * globs and backslashes literal in sh, bash, zsh and tcsh alike.
 *
 * Three characters have no portable form and are refused instead of
 * producing a line that works in three shells out of four:
 *   - `'` cannot appear inside single quotes, and the usual `'\''`
 *     trick is not valid csh;
 *   - `!` triggers history expansion in interactive tcsh even inside
 *     single quotes (`'a!b'` gives "Event not found"), while the csh
 *     escape `\!` stays a literal backslash in the other three;
 *   - a newline ends the command in tcsh ("Unmatched '").
 */
export function quoteForPosixShell(arg: string): string {
    if (arg.includes("'")) {
        throw new UnquotableError(arg, 'it contains a single quote (\')');
    }
    if (arg.includes('!')) {
        throw new UnquotableError(arg,
            'it contains "!", which tcsh expands even inside quotes');
    }
    if (/[\r\n]/.test(arg)) {
        throw new UnquotableError(arg, 'it contains a line break');
    }
    return `'${arg}'`;
}

/* ------------------------------------------------------------------ */
/*  The command line                                                  */
/* ------------------------------------------------------------------ */

/** Where gelb-run writes its output: `<outputFolder>/<basename>.nc`. */
export function outputFileFor(file: string, outputFolder?: string): string {
    const folder = outputFolder ?? path.dirname(file);
    return path.join(folder, path.basename(file, '.gelb') + '.nc');
}

function checkCount(name: string, n: number, min: number): void {
    if (!Number.isInteger(n) || n < min) {
        throw new RangeError(`${name} must be an integer >= ${min}, got ${n}`);
    }
}

/** gelb-run's arguments, each passed through `quote` where a value
 *  may need it (the -D pairs and the file). */
function runArgs(
    file: string, params: RunParams, quote: (s: string) => string,
): string[] {
    checkCount('time steps', params.timeSteps, 1);
    checkCount('write every', params.writeEvery, 1);
    if (params.seed !== undefined) checkCount('seed', params.seed, 0);

    const parts: string[] = [];
    parts.push('-n', String(params.timeSteps));
    parts.push('-w', String(params.writeEvery));
    for (const [name, value] of params.defines) {
        parts.push('-D', quote(`${name}=${value}`));
    }
    if (params.seed !== undefined) parts.push('-s', String(params.seed));
    if (params.backend !== DEFAULT_BACKEND) parts.push('-b', params.backend);
    if (params.view) parts.push('--view');
    parts.push(quote(file));
    return parts;
}

/**
 * The arguments after gelb-run, as the Run view's task passes them to
 * the process (no shell, so no quoting), e.g.
 *
 *   -n 40000 -w 1000 -D N=257 --view /ex/cavity.gelb
 *
 * Throws RangeError for a count that is not a positive integer.
 */
export function buildRunArgs(file: string, params: RunParams): string[] {
    return runArgs(file, params, s => s);
}

/**
 * The same run as one shell line, with its own `cd` into the output
 * folder, e.g.
 *
 *   cd '/runs' && '/gelb/bin/gelb-run' -n 40000 -w 1000 -D 'N=257' --view '/ex/cavity.gelb'
 *
 * What VS Code's task shell runs for a bare gelb-run, which only a
 * shell's PATH finds. `cmd` is the executable (bare name or path, see
 * resolveRunExecutable) and is quoted whole. Throws UnquotableError for
 * a path or value the shells cannot all take, and RangeError for a
 * count that is not a positive integer.
 */
export function buildRunCommandLine(
    cmd: string,
    file: string,
    params: RunParams,
): string {
    const folder = params.outputFolder ?? path.dirname(file);
    return ['cd', quoteForPosixShell(folder), '&&', quoteForPosixShell(cmd),
        ...runArgs(file, params, quoteForPosixShell)].join(' ');
}

/** `arg` in single quotes for a reader (and for sh, bash and zsh): a
 *  single quote inside becomes '\''. Never throws; the Run view's log
 *  shows a run this way, whichever way it was launched. */
export function quoteForDisplay(arg: string): string {
    return `'${arg.split("'").join(`'\\''`)}'`;
}

/** The shell line of buildRunCommandLine for the log: the same form,
 *  with quoteForDisplay, so any path or value can be shown. */
export function displayRunCommandLine(
    cmd: string, file: string, params: RunParams,
): string {
    const folder = params.outputFolder ?? path.dirname(file);
    return ['cd', quoteForDisplay(folder), '&&', quoteForDisplay(cmd),
        ...runArgs(file, params, quoteForDisplay)].join(' ');
}

/**
 * Turn the `gelb.gelbRunCommand` setting into the executable the run
 * starts. A bare name (`gelb-run`) is left to the task shell's PATH;
 * `~/...` is expanded; a relative path such as `./scripts/gelb-run` is
 * resolved against `baseDir` (the workspace folder), because the run
 * starts in the output folder.
 */
export function resolveRunExecutable(
    cmd: string, baseDir: string, homeDir: string,
): string {
    const c = cmd.trim();
    if (c === '~') return homeDir;
    if (c.startsWith('~/')) return path.join(homeDir, c.slice(2));
    if (path.isAbsolute(c) || !c.includes('/')) return c;
    return path.resolve(baseDir, c);
}

/**
 * Resolve the `gelb.runOutputFolder` setting: empty = next to the
 * source (returns undefined), `~` and `${workspaceFolder}` expanded,
 * relative paths taken from `workspaceDir`.
 */
export function resolveOutputFolderSetting(
    setting: string, workspaceDir: string | undefined, homeDir: string,
): string | undefined {
    let s = setting.trim();
    if (!s) return undefined;
    if (workspaceDir) s = s.split('${workspaceFolder}').join(workspaceDir);
    if (s === '~') return homeDir;
    if (s.startsWith('~/')) return path.join(homeDir, s.slice(2));
    if (path.isAbsolute(s)) return path.resolve(s);
    return workspaceDir ? path.resolve(workspaceDir, s) : undefined;
}

/* ------------------------------------------------------------------ */
/*  Tokenizer for the gelbc / gelb-view command settings              */
/* ------------------------------------------------------------------ */

/**
 * Split a command setting such as `uv run gelbc` or
 * `"/Users/me/My Tools/gelbc" --flag` into executable and arguments.
 * Whitespace separates words; single quotes group literally; double
 * quotes group, and inside them a backslash escapes only `"`, `\`, `$`
 * and a backquote, as in POSIX sh; adjacent quoted and unquoted pieces
 * join into one word (`a"b c"d` is `ab cd`). Any other backslash is
 * kept as is, quoted or not, so Windows-style paths survive
 * (`"C:\Program Files\GeLB\gelbc.exe"`). An unterminated quote runs to
 * the end of the string.
 */
export function tokenizeCommand(cmd: string): string[] {
    const words: string[] = [];
    let cur = '';
    let inWord = false;
    let i = 0;
    const n = cmd.length;
    while (i < n) {
        const c = cmd[i];
        if (/\s/.test(c)) {
            if (inWord) { words.push(cur); cur = ''; inWord = false; }
            i++;
        } else if (c === "'") {
            inWord = true;
            i++;
            while (i < n && cmd[i] !== "'") cur += cmd[i++];
            i++;                                   // closing quote
        } else if (c === '"') {
            inWord = true;
            i++;
            while (i < n && cmd[i] !== '"') {
                if (cmd[i] === '\\' && i + 1 < n && '"\\$`'.includes(cmd[i + 1])) {
                    cur += cmd[i + 1];
                    i += 2;
                } else {
                    cur += cmd[i++];
                }
            }
            i++;                                   // closing quote
        } else {
            inWord = true;
            cur += c;
            i++;
        }
    }
    if (inWord) words.push(cur);
    return words;
}

/* ------------------------------------------------------------------ */
/*  random() detection                                                */
/* ------------------------------------------------------------------ */

/** True when the program calls the `random()` intrinsic outside
 *  comments and string literals; the Run view shows the seed row only
 *  then. */
export function sourceCallsRandom(source: string): boolean {
    return /\brandom\s*\(/.test(stripCommentsAndStrings(source));
}

/** 0-based line of the first `simulation_description(` outside
 *  comments, where the Run CodeLens sits; 0 when there is none. */
export function runLensLine(source: string): number {
    const lines = stripCommentsAndStrings(source).split('\n');
    const i = lines.findIndex(l => /^\s*simulation_description\s*\(/.test(l));
    return i < 0 ? 0 : i;
}
