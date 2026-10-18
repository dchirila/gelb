/**
 * Extension Development Host tests (test/suite): the real VS Code with
 * this extension and nothing else, in a throwaway profile, on a copy of
 * the fixture in a temporary folder. Two launches: a window with that
 * folder open, then a window without a folder.
 *
 *   xvfb-run -a -s "-screen 0 1600x1000x24" npm run test:vscode
 *
 * (on Linux with WAYLAND_DISPLAY unset, so nothing appears on the
 * desktop). VS Code is GELB_VSCODE, else /usr/share/code/code when it
 * exists, else a download by @vscode/test-electron. GELB_TEST_REAL=1
 * adds the tests with the real scripts/gelb-run of this checkout;
 * GELB_TEST_SUITES=real (words of the suite names, comma-separated)
 * runs only some.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

/** The environment of the VS Code under test: none of the variables of
 *  a VS Code this may be started from (an integrated terminal), which
 *  would make it a Node process or talk to that instance. */
function cleanEnv() {
    for (const k of Object.keys(process.env)) {
        if (/^(ELECTRON_|VSCODE_)/.test(k) || k === 'WAYLAND_DISPLAY') {
            delete process.env[k];
        }
    }
}

function writeJson(p, value) {
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(value, null, 2));
}

async function launch(name, { folder, files, env, settings }) {
    // Short: VS Code's IPC socket lives in the user data folder.
    const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'gvt-'));
    const extensions = fs.mkdtempSync(path.join(os.tmpdir(), 'gvt-ext-'));
    writeJson(path.join(userData, 'User', 'settings.json'), settings);
    const exe = process.env.GELB_VSCODE
        || (fs.existsSync('/usr/share/code/code') ? '/usr/share/code/code' : undefined);
    const args = [
        '--user-data-dir', userData,
        '--extensions-dir', extensions,
        '--disable-extensions',
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes',
        '--password-store=basic',
    ];
    if (process.platform === 'linux') args.push('--ozone-platform=x11');
    if (folder) args.push(folder);
    console.log(`\n=== ${name} ===`);
    try {
        await runTests({
            vscodeExecutablePath: exe,
            extensionDevelopmentPath: path.resolve(__dirname, '..'),
            extensionTestsPath: path.resolve(__dirname, 'suite', 'index'),
            launchArgs: args,
            extensionTestsEnv: { ...env, GELB_SUITE_FILES: files.join(',') },
        });
    } finally {
        fs.rmSync(userData, { recursive: true, force: true });
        fs.rmSync(extensions, { recursive: true, force: true });
    }
}

async function main() {
    cleanEnv();
    const fixture = path.resolve(__dirname, 'suite', 'fixture');
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gelb-run-test-'));
    const ws = path.join(root, 'ws');
    const sims = path.join(ws, 'my sims');
    const bin = path.join(root, 'bin');
    const shellOnly = path.join(root, 'shell only');
    fs.mkdirSync(sims, { recursive: true });
    fs.mkdirSync(bin);
    fs.mkdirSync(shellOnly);
    fs.copyFileSync(path.join(fixture, 'cavity.gelb'), path.join(sims, 'cavity.gelb'));
    fs.copyFileSync(path.join(fixture, 'cavity.gelb'), path.join(ws, 'other.gelb'));
    for (const dir of [bin, shellOnly]) {
        fs.copyFileSync(path.join(fixture, 'fake-gelb-run'), path.join(dir, 'fake-gelb-run'));
        fs.chmodSync(path.join(dir, 'fake-gelb-run'), 0o755);
    }
    // Startup file of the task shell (bash): a cd elsewhere, as a user's
    // shell startup file may do. Scripts (fake-gelb-run, gelb-run)
    // read it too, as non-interactive bash, and are left alone.
    const bashEnv = path.join(root, 'bash_env');
    fs.writeFileSync(bashEnv, 'case "$0" in bash|*/bash) '
        + `echo "$PWD" >> '${path.join(root, 'bash_env.read')}'; cd / ;; esac\n`);
    const env = {
        GELB_TEST_ROOT: root,
        GELB_TEST_WS: ws,
        GELB_TEST_STUB: path.join(bin, 'fake-gelb-run'),
        GELB_TEST_SHELL_STUB_DIR: shellOnly,
        GELB_TEST_CHECKOUT: path.resolve(__dirname, '..', '..'),
    };
    const settings = {
        'gelb.lintOnOpen': false,
        'gelb.lintOnSave': false,
        'gelb.gelbRunCommand': env.GELB_TEST_STUB,
        'terminal.integrated.env.linux': {
            PATH: `${shellOnly}:\${env:PATH}`,
            BASH_ENV: bashEnv,
        },
        'terminal.integrated.env.osx': {
            PATH: `${shellOnly}:\${env:PATH}`,
            BASH_ENV: bashEnv,
        },
        'workbench.startupEditor': 'none',
        'security.workspace.trust.enabled': false,
    };
    // The real gelb-run may start bash itself: no startup cd there.
    const realSettings = {
        ...settings,
        'terminal.integrated.env.linux': {}, 'terminal.integrated.env.osx': {},
    };
    let failed = false;
    const suites = [
        ['window with a folder', { folder: ws, files: ['run.test.js'], settings }],
        ['window without a folder',
            { folder: undefined, files: ['folderless.test.js'], settings }],
    ];
    if (process.env.GELB_TEST_REAL === '1') {
        suites.push(['the real gelb-run',
            { folder: ws, files: ['real.test.js'], settings: realSettings }]);
    }
    const only = process.env.GELB_TEST_SUITES?.split(',');
    for (const [name, o] of suites) {
        if (only && !only.some(k => name.includes(k))) continue;
        try {
            await launch(name, { ...o, env });
        } catch (e) {
            console.error(`${name}: ${e.message ?? e}`);
            failed = true;
        }
    }
    fs.rmSync(root, { recursive: true, force: true });
    process.exit(failed ? 1 : 0);
}

main();
