const assert = require('assert');

const { findGelbRoot, resolveTool } = require('../out/gelbTools');


/** A fake host: `files` are regular files, `exes` executable ones. */
function host({ files = [], exes = [], pathEnv = '/usr/bin:/bin', platform = 'darwin' } = {}) {
    const f = new Set([...files, ...exes]);
    const x = new Set(exes);
    return { platform, home: '/Users/me', pathEnv, isFile: p => f.has(p), isExecutable: p => x.has(p) };
}

const SRC = '/Users/me/src/gelb';
const CHECKOUT = [`${SRC}/pyproject.toml`, `${SRC}/gelb/gelbc.py`];
const CHECKOUT_EXES = [`${SRC}/scripts/gelb-run`];
const VENV = [`${SRC}/.venv/bin/gelbc`, `${SRC}/.venv/bin/gelb-view`];
const EXAMPLE_DIR = `${SRC}/examples/lbm/2d`;


describe('resolveTool: a GeLB source checkout', () => {
    const h = host({ files: CHECKOUT, exes: [...CHECKOUT_EXES, ...VENV, '/usr/bin/gelbc'] });

    it('uses scripts/gelb-run for a file inside the checkout', () => {
        assert.deepStrictEqual(resolveTool('gelb-run', [EXAMPLE_DIR], h).argv,
            [`${SRC}/scripts/gelb-run`]);
    });

    it('uses the checkout .venv for gelbc and gelb-view, ahead of the PATH', () => {
        assert.deepStrictEqual(resolveTool('gelbc', [EXAMPLE_DIR], h).argv, [`${SRC}/.venv/bin/gelbc`]);
        assert.deepStrictEqual(resolveTool('gelb-view', [EXAMPLE_DIR], h).argv, [`${SRC}/.venv/bin/gelb-view`]);
    });

    it('finds the checkout through the workspace folder for a file elsewhere', () => {
        assert.deepStrictEqual(resolveTool('gelb-run', ['/tmp/scratch', SRC], h).argv,
            [`${SRC}/scripts/gelb-run`]);
    });

    it('falls back to uv run --project without a .venv', () => {
        const u = host({ files: CHECKOUT, exes: [...CHECKOUT_EXES, '/opt/homebrew/bin/uv'],
                         pathEnv: '/opt/homebrew/bin:/usr/bin' });
        assert.deepStrictEqual(resolveTool('gelbc', [EXAMPLE_DIR], u).argv,
            ['/opt/homebrew/bin/uv', 'run', '--project', SRC, 'gelbc']);
        const local = host({ files: CHECKOUT, exes: [...CHECKOUT_EXES, '/Users/me/.local/bin/uv'] });
        assert.deepStrictEqual(resolveTool('gelb-view', [EXAMPLE_DIR], local).argv,
            ['/Users/me/.local/bin/uv', 'run', '--project', SRC, 'gelb-view']);
    });

    it('says how to set the checkout up when it has neither .venv nor uv', () => {
        const bare = host({ files: CHECKOUT, exes: [...CHECKOUT_EXES, '/usr/bin/gelbc'] });
        const r = resolveTool('gelbc', [EXAMPLE_DIR], bare);
        assert.strictEqual(r.argv, undefined, 'no other gelbc is picked instead');
        assert.match(r.hint, /gelb_bootstrap\.sh/);
        assert.match(r.hint, /gelb\.gelbcCommand/);
    });

    it('uses .venv\\Scripts\\<tool>.exe on Windows', () => {
        const w = host({ files: CHECKOUT, exes: [...CHECKOUT_EXES, `${SRC}/.venv/Scripts/gelbc.exe`],
                         platform: 'win32', pathEnv: '' });
        assert.deepStrictEqual(resolveTool('gelbc', [EXAMPLE_DIR], w).argv, [`${SRC}/.venv/Scripts/gelbc.exe`]);
    });

    it('needs all three markers: a pyproject.toml alone is not a checkout', () => {
        const other = host({ files: [`${SRC}/pyproject.toml`], exes: [`${SRC}/scripts/gelb-run`] });
        assert.strictEqual(findGelbRoot(EXAMPLE_DIR, other), undefined);
    });
});


describe('resolveTool: installations and the PATH', () => {
    it('uses bin/<tool> of a bundle above the file', () => {
        const b = host({ files: ['/Volumes/x/GeLB/bin/gelb-env.sh'], exes: ['/Volumes/x/GeLB/bin/gelb-run'] });
        assert.deepStrictEqual(resolveTool('gelb-run', ['/Volumes/x/GeLB/examples/lbm/2d'], b).argv,
            ['/Volumes/x/GeLB/bin/gelb-run']);
    });

    it('takes the tool from the PATH outside a checkout', () => {
        const p = host({ exes: ['/opt/gelb/bin/gelbc'], pathEnv: '/usr/bin:/opt/gelb/bin' });
        assert.deepStrictEqual(resolveTool('gelbc', ['/tmp/sims'], p).argv, ['/opt/gelb/bin/gelbc']);
    });

    it('falls back to ~/gelb/bin, where the macOS installer puts GeLB', () => {
        const i = host({ exes: ['/Users/me/gelb/bin/gelb-run'] });
        assert.deepStrictEqual(resolveTool('gelb-run', ['/tmp/sims'], i).argv, ['/Users/me/gelb/bin/gelb-run']);
    });

    it('names the setting when gelbc or gelb-view is not found', () => {
        const r = resolveTool('gelbc', ['/tmp/sims'], host());
        assert.strictEqual(r.argv, undefined);
        assert.match(r.hint, /cannot find gelbc/);
        assert.match(r.hint, /gelb\.gelbcCommand/);
    });

    it("leaves gelb-run to the task shell's PATH when nothing else finds it", () => {
        const r = resolveTool('gelb-run', ['/tmp/sims'], host());
        assert.deepStrictEqual(r.argv, ['gelb-run']);
        assert.strictEqual(r.terminalPath, true);
        assert.match(r.from, /task shell/);
    });

    it('says where each tool was found', () => {
        const h = host({ files: CHECKOUT, exes: [...CHECKOUT_EXES, ...VENV] });
        assert.match(resolveTool('gelb-run', [EXAMPLE_DIR], h).from,
            new RegExp(`source checkout ${SRC}$`));
        assert.strictEqual(resolveTool('gelb-run', ['/tmp'],
            host({ exes: ['/usr/bin/gelb-run'] })).from, 'the PATH');
    });
});
