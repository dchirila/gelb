/**
 * The command line for gelbc, gelb-view or gelb-run on behalf of a
 * .gelb file: its setting when one is given, else found by the search
 * in gelbTools.ts (source checkout, bundle, PATH, ~/gelb).
 */

import * as vscode from 'vscode';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { GelbTool, TOOL_SETTING, ToolHost, resolveTool } from './gelbTools';
import { resolveRunExecutable, tokenizeCommand } from './runCommand';

function isFile(p: string): boolean {
    try {
        return fs.statSync(p).isFile();
    } catch {
        return false;
    }
}

const nodeHost: ToolHost = {
    platform: process.platform,
    home: os.homedir(),
    get pathEnv() { return process.env.PATH ?? ''; },
    isFile,
    isExecutable: (p) => {
        try {
            fs.accessSync(p, fs.constants.X_OK);
            return isFile(p);
        } catch {
            return false;
        }
    },
};

/** Where to look for a checkout or bundle: the file's folder, its
 *  workspace folder, then the other workspace folders. */
function startDirs(uri: vscode.Uri): string[] {
    const dirs = [path.dirname(uri.fsPath)];
    const own = vscode.workspace.getWorkspaceFolder(uri);
    if (own) dirs.push(own.uri.fsPath);
    for (const f of vscode.workspace.workspaceFolders ?? []) dirs.push(f.uri.fsPath);
    return [...new Set(dirs)];
}

export type ToolCommand =
    | { argv: string[]; from: string; error?: undefined; terminalPath?: boolean }
    | { argv?: undefined; from?: undefined; error: string; terminalPath?: undefined };

/**
 * `argv` is the executable and its leading arguments (for gelb-run a
 * single executable); `from` says where it was found; `error` says why
 * there is none; `terminalPath` marks the bare gelb-run left to the
 * task shell's PATH (gelbTools.ts, step 5).
 */
export function toolCommand(tool: GelbTool, uri: vscode.Uri): ToolCommand {
    const key = TOOL_SETTING[tool].replace(/^gelb\./, '');
    const setting = vscode.workspace.getConfiguration('gelb', uri)
        .get<string>(key, '').trim();
    if (setting) {
        if (tool === 'gelb-run') {
            const ws = vscode.workspace.getWorkspaceFolder(uri);
            return {
                argv: [resolveRunExecutable(
                    setting, ws?.uri.fsPath ?? path.dirname(uri.fsPath), os.homedir())],
                from: `the setting ${TOOL_SETTING[tool]}`,
            };
        }
        return { argv: tokenizeCommand(setting), from: `the setting ${TOOL_SETTING[tool]}` };
    }
    const r = resolveTool(tool, startDirs(uri), nodeHost);
    return r.argv
        ? { argv: r.argv, from: r.from, terminalPath: r.terminalPath }
        : { error: r.hint };
}

/** Show `error` from toolCommand with a button to the setting. */
export async function reportMissingTool(tool: GelbTool, error: string): Promise<void> {
    const open = 'Open Settings';
    const choice = await vscode.window.showErrorMessage(`GeLB: ${error}.`, open);
    if (choice === open) {
        vscode.commands.executeCommand('workbench.action.openSettings', TOOL_SETTING[tool]);
    }
}
