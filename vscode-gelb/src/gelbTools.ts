/**
 * Where the extension finds gelbc, gelb-view and gelb-run when their
 * settings (`gelb.gelbcCommand`, `gelb.gelbViewCommand`,
 * `gelb.gelbRunCommand`) are left empty, the default.
 *
 * Searched from the .gelb file's folder and the workspace folders
 * upwards, nearest first:
 *   1. a GeLB source checkout (pyproject.toml, gelb/gelbc.py and
 *      scripts/gelb-run): gelb-run is its scripts/gelb-run; gelbc and
 *      gelb-view come from its .venv (what scripts/gelb_bootstrap.sh
 *      creates), else through `uv run --project <checkout>`;
 *   2. a relocatable GeLB bundle (bin/gelb-env.sh): its bin/<tool>;
 * then
 *   3. <tool> on the PATH;
 *   4. ~/gelb/bin/<tool>, where the macOS installer puts GeLB;
 *   5. for gelb-run only, the bare name: the Run view then runs it
 *      through VS Code's task shell, whose PATH can be longer than
 *      VS Code's own (terminal.integrated.env.*, what the shell reads
 *      when it starts), so that shell gets the last word.
 *
 * No `vscode` import here, so mocha can test this module from `out/`
 * without starting VS Code (see test/gelbTools.test.js).
 */

import * as path from 'path';

export type GelbTool = 'gelbc' | 'gelb-view' | 'gelb-run';

/** The setting that overrides the search for each tool. */
export const TOOL_SETTING: Readonly<Record<GelbTool, string>> = {
    'gelbc': 'gelb.gelbcCommand',
    'gelb-view': 'gelb.gelbViewCommand',
    'gelb-run': 'gelb.gelbRunCommand',
};

/** What the search may look at: the file system, PATH and home. */
export interface ToolHost {
    platform: string;
    home: string;
    /** The PATH environment variable. */
    pathEnv: string;
    isFile(p: string): boolean;
    isExecutable(p: string): boolean;
}

/** A command (executable and leading arguments) and where it was
 *  found (`from`, for the Run view's log), or why none was found.
 *  `terminalPath`: the bare gelb-run of step 5, which only a shell can
 *  resolve. */
export type ToolResolution =
    | { argv: string[]; from: string; hint?: undefined; terminalPath?: boolean }
    | { argv?: undefined; from?: undefined; hint: string; terminalPath?: undefined };

function exeNames(tool: string, host: ToolHost): string[] {
    return host.platform === 'win32' ? [`${tool}.exe`, `${tool}.cmd`] : [tool];
}

/** The first executable called `tool` on the PATH. */
export function onPath(tool: string, host: ToolHost): string | undefined {
    const sep = host.platform === 'win32' ? ';' : ':';
    for (const dir of host.pathEnv.split(sep)) {
        if (!dir) continue;
        for (const name of exeNames(tool, host)) {
            const p = path.join(dir, name);
            if (host.isExecutable(p)) return p;
        }
    }
    return undefined;
}

/** uv, where gelb-run and the uv installer put it. */
export function findUv(host: ToolHost): string | undefined {
    const found = onPath('uv', host);
    if (found) return found;
    for (const dir of ['.local/bin', '.cargo/bin']) {
        const p = path.join(host.home, dir, 'uv');
        if (host.isExecutable(p)) return p;
    }
    return undefined;
}

function isCheckout(dir: string, host: ToolHost): boolean {
    return host.isFile(path.join(dir, 'pyproject.toml'))
        && host.isFile(path.join(dir, 'gelb', 'gelbc.py'))
        && host.isFile(path.join(dir, 'scripts', 'gelb-run'));
}

function isBundle(dir: string, host: ToolHost): boolean {
    return host.isFile(path.join(dir, 'bin', 'gelb-env.sh'));
}

/** The nearest GeLB source checkout or bundle at or above `dir`. */
export function findGelbRoot(
    dir: string, host: ToolHost,
): { kind: 'checkout' | 'bundle'; root: string } | undefined {
    let d = path.resolve(dir);
    for (;;) {
        if (isCheckout(d, host)) return { kind: 'checkout', root: d };
        if (isBundle(d, host)) return { kind: 'bundle', root: d };
        const up = path.dirname(d);
        if (up === d) return undefined;
        d = up;
    }
}

function fromCheckout(
    tool: GelbTool, root: string, host: ToolHost,
): ToolResolution {
    const from = `the GeLB source checkout ${root}`;
    if (tool === 'gelb-run') return { argv: [path.join(root, 'scripts', 'gelb-run')], from };
    const venv = host.platform === 'win32'
        ? exeNames(tool, host).map(n => path.join(root, '.venv', 'Scripts', n))
        : [path.join(root, '.venv', 'bin', tool)];
    const inVenv = venv.find(p => host.isExecutable(p));
    if (inVenv) return { argv: [inVenv], from };
    const uv = findUv(host);
    if (uv) return { argv: [uv, 'run', '--project', root, tool], from };
    return {
        hint: `the GeLB source checkout ${root} has no .venv and uv was `
            + 'not found; run ./scripts/gelb_bootstrap.sh there, or set '
            + `"${TOOL_SETTING[tool]}"`,
    };
}

/**
 * The command that runs `tool` for a file, searched from `startDirs`
 * (the file's folder first, then the workspace folders) as described
 * at the top of this module. A checkout that is found decides: its
 * tools are used, or the hint says how to set it up, rather than an
 * installation elsewhere being picked instead.
 */
export function resolveTool(
    tool: GelbTool, startDirs: string[], host: ToolHost,
): ToolResolution {
    for (const dir of startDirs) {
        const found = findGelbRoot(dir, host);
        if (found?.kind === 'checkout') return fromCheckout(tool, found.root, host);
        if (found?.kind === 'bundle') {
            const p = path.join(found.root, 'bin', tool);
            if (host.isExecutable(p)) {
                return { argv: [p], from: `the GeLB installation ${found.root}` };
            }
        }
    }
    const inPath = onPath(tool, host);
    if (inPath) return { argv: [inPath], from: 'the PATH' };
    const installed = path.join(host.home, 'gelb', 'bin', tool);
    if (host.platform !== 'win32' && host.isExecutable(installed)) {
        return { argv: [installed], from: 'the GeLB installation ~/gelb' };
    }
    if (tool === 'gelb-run') {
        return {
            argv: ['gelb-run'], terminalPath: true,
            from: "nowhere VS Code can see; left to the task shell's PATH",
        };
    }
    return {
        hint: `cannot find ${tool}. Open the .gelb file (or a workspace) `
            + 'inside a GeLB source checkout set up with '
            + './scripts/gelb_bootstrap.sh or inside a GeLB installation, '
            + `put ${tool} on the PATH, or set "${TOOL_SETTING[tool]}"`,
    };
}
