const assert = require('assert');

const {
    UnquotableError,
    buildRunArgs,
    buildRunCommandLine,
    displayRunCommandLine,
    outputFileFor,
    quoteForDisplay,
    quoteForPosixShell,
    resolveOutputFolderSetting,
    resolveRunExecutable,
    runLensLine,
    sourceCallsRandom,
    tokenizeCommand,
} = require('../out/runCommand');


const FILE = '/Users/gerrit/gelb/examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb';
const EXE = '/Users/gerrit/gelb/bin/gelb-run';

function params(overrides = {}) {
    return {
        timeSteps: 1000,
        writeEvery: 100,
        defines: [],
        backend: 'cpu_highway',
        view: false,
        ...overrides,
    };
}


describe('quoteForPosixShell', () => {
    it('single-quotes a plain word', () => {
        assert.strictEqual(quoteForPosixShell('N=257'), "'N=257'");
    });

    it('keeps spaces inside the quotes', () => {
        assert.strictEqual(
            quoteForPosixShell('/Users/me/My Runs'), "'/Users/me/My Runs'");
    });

    it('keeps $, backquotes, globs and backslashes literal', () => {
        assert.strictEqual(
            quoteForPosixShell('$HOME `x` *.nc \\t'), "'$HOME `x` *.nc \\t'");
    });

    it('rejects a single quote', () => {
        assert.throws(() => quoteForPosixShell("it's"), UnquotableError);
    });

    it('rejects "!", which interactive tcsh expands inside quotes', () => {
        assert.throws(() => quoteForPosixShell('/tmp/wow!'), UnquotableError);
    });

    it('rejects a line break', () => {
        assert.throws(() => quoteForPosixShell('a\nb'), UnquotableError);
    });

    it('names the offending value in the error', () => {
        try {
            quoteForPosixShell("O'Brien");
            assert.fail('no error');
        } catch (e) {
            assert.ok(e instanceof UnquotableError);
            assert.strictEqual(e.value, "O'Brien");
            assert.match(e.message, /single quote/);
        }
    });
});


describe('buildRunCommandLine', () => {
    it('builds the default line with a cd prefix', () => {
        assert.strictEqual(
            buildRunCommandLine(EXE, FILE, params()),
            "cd '/Users/gerrit/gelb/examples/lbm/2d' && " +
            `'${EXE}' -n 1000 -w 100 '${FILE}'`);
    });

    it('always starts with its own cd, into the output folder', () => {
        const line = buildRunCommandLine(EXE, FILE,
            params({ outputFolder: '/Users/gerrit/runs' }));
        assert.ok(line.startsWith("cd '/Users/gerrit/runs' && "), line);
    });

    it('emits every row: the example line of the work order', () => {
        assert.strictEqual(
            buildRunCommandLine(EXE, FILE, params({
                timeSteps: 40000,
                writeEvery: 1000,
                defines: [['N', '257']],
                view: true,
                outputFolder: '/Users/gerrit/runs',
            })),
            "cd '/Users/gerrit/runs' && " +
            `'${EXE}' -n 40000 -w 1000 -D 'N=257' --view '${FILE}'`);
    });

    it('emits -D once per pair, in order', () => {
        const line = buildRunCommandLine(EXE, FILE, params({
            defines: [['N', '257'], ['U_LID', '0.2'], ['TAU', '0.6']],
        }));
        assert.ok(line.includes("-D 'N=257' -D 'U_LID=0.2' -D 'TAU=0.6'"), line);
    });

    it('emits -s only when a seed is set', () => {
        assert.ok(!buildRunCommandLine(EXE, FILE, params()).includes(' -s '));
        assert.ok(buildRunCommandLine(EXE, FILE, params({ seed: 0 }))
            .includes(' -s 0 '));
        assert.ok(buildRunCommandLine(EXE, FILE, params({ seed: 42 }))
            .includes(' -s 42 '));
    });

    it('emits -b only for a non-default backend', () => {
        assert.ok(!buildRunCommandLine(EXE, FILE, params()).includes(' -b '));
        assert.ok(buildRunCommandLine(EXE, FILE,
            params({ backend: 'cpu_fortran_serial' }))
            .includes(' -b cpu_fortran_serial '));
        assert.ok(buildRunCommandLine(EXE, FILE,
            params({ backend: 'gpu_cuda_cpp' }))
            .includes(' -b gpu_cuda_cpp '));
    });

    it('emits --view only when the toggle is on', () => {
        assert.ok(!buildRunCommandLine(EXE, FILE, params()).includes('--view'));
        assert.ok(buildRunCommandLine(EXE, FILE, params({ view: true }))
            .includes(' --view '));
    });

    it('quotes a bare command name and paths with spaces', () => {
        const file = '/Users/me/My Sims/cavity.gelb';
        assert.strictEqual(
            buildRunCommandLine('gelb-run', file, params()),
            `cd '/Users/me/My Sims' && 'gelb-run' -n 1000 -w 100 '${file}'`);
    });

    it('passes a -D value verbatim inside the quotes', () => {
        const line = buildRunCommandLine(EXE, FILE,
            params({ defines: [['TAU', '1.0 / 1.6'], ['X', '$HOME']] }));
        assert.ok(line.includes("-D 'TAU=1.0 / 1.6' -D 'X=$HOME'"), line);
    });

    it('refuses an unquotable -D value or path', () => {
        assert.throws(() => buildRunCommandLine(EXE, FILE,
            params({ defines: [['N', "2'"]] })), UnquotableError);
        assert.throws(() => buildRunCommandLine(EXE, "/tmp/it's.gelb",
            params()), UnquotableError);
        assert.throws(() => buildRunCommandLine(EXE, FILE,
            params({ outputFolder: '/tmp/wow!' })), UnquotableError);
    });

    it('refuses counts that are not positive integers', () => {
        assert.throws(() => buildRunCommandLine(EXE, FILE,
            params({ timeSteps: 0 })), RangeError);
        assert.throws(() => buildRunCommandLine(EXE, FILE,
            params({ writeEvery: 2.5 })), RangeError);
        assert.throws(() => buildRunCommandLine(EXE, FILE,
            params({ seed: -1 })), RangeError);
    });

    it('allows write-every larger than the time steps', () => {
        assert.ok(buildRunCommandLine(EXE, FILE,
            params({ timeSteps: 10, writeEvery: 100 })).includes('-n 10 -w 100'));
    });
});


describe('buildRunArgs', () => {
    it('gives the arguments as a vector, unquoted', () => {
        assert.deepStrictEqual(buildRunArgs(FILE, params()),
            ['-n', '1000', '-w', '100', FILE]);
    });

    it('keeps spaces, quotes and "!" inside one argument each', () => {
        const file = "/Users/me/O'Brien's runs!/cavity.gelb";
        assert.deepStrictEqual(
            buildRunArgs(file, params({
                defines: [['TAU', '1.0 / 1.6'], ['X', "it's"]],
                seed: 7, backend: 'cpu_fortran_serial', view: true,
            })),
            ['-n', '1000', '-w', '100', '-D', 'TAU=1.0 / 1.6', '-D', "X=it's",
                '-s', '7', '-b', 'cpu_fortran_serial', '--view', file]);
    });

    it('refuses counts that are not positive integers', () => {
        assert.throws(() => buildRunArgs(FILE, params({ timeSteps: 0 })), RangeError);
    });
});


describe('displayRunCommandLine', () => {
    it('is the shell line, for the log', () => {
        assert.strictEqual(
            displayRunCommandLine(EXE, FILE, params({ defines: [['N', '257']] })),
            buildRunCommandLine(EXE, FILE, params({ defines: [['N', '257']] })));
    });

    it('shows what the shell line refuses', () => {
        assert.strictEqual(quoteForDisplay("it's"), `'it'\\''s'`);
        const line = displayRunCommandLine(EXE, "/tmp/it's!.gelb", params());
        assert.ok(line.endsWith(`'/tmp/it'\\''s!.gelb'`), line);
    });
});


describe('outputFileFor', () => {
    it('is <basename>.nc next to the source by default', () => {
        assert.strictEqual(outputFileFor(FILE),
            '/Users/gerrit/gelb/examples/lbm/2d/lid_driven_cavity_2d_bgk.nc');
    });

    it('is <basename>.nc in the output folder', () => {
        assert.strictEqual(outputFileFor(FILE, '/Users/gerrit/runs'),
            '/Users/gerrit/runs/lid_driven_cavity_2d_bgk.nc');
    });
});


describe('resolveRunExecutable', () => {
    it('leaves a bare name to the PATH', () => {
        assert.strictEqual(resolveRunExecutable('gelb-run', '/ws', '/h'), 'gelb-run');
    });

    it('keeps an absolute path, spaces included', () => {
        assert.strictEqual(
            resolveRunExecutable(' /My Tools/gelb-run ', '/ws', '/h'),
            '/My Tools/gelb-run');
    });

    it('resolves a relative path against the workspace folder', () => {
        assert.strictEqual(
            resolveRunExecutable('./scripts/gelb-run', '/Users/me/gelb', '/h'),
            '/Users/me/gelb/scripts/gelb-run');
    });

    it('expands ~/', () => {
        assert.strictEqual(
            resolveRunExecutable('~/gelb/bin/gelb-run', '/ws', '/Users/me'),
            '/Users/me/gelb/bin/gelb-run');
    });
});


describe('resolveOutputFolderSetting', () => {
    it('is undefined (next to the source) when empty', () => {
        assert.strictEqual(resolveOutputFolderSetting('  ', '/ws', '/h'), undefined);
    });

    it('expands ~ and ${workspaceFolder}; relative is from the workspace', () => {
        assert.strictEqual(resolveOutputFolderSetting('~/runs', '/ws', '/h'), '/h/runs');
        assert.strictEqual(
            resolveOutputFolderSetting('${workspaceFolder}/runs', '/ws', '/h'),
            '/ws/runs');
        assert.strictEqual(resolveOutputFolderSetting('runs', '/ws', '/h'), '/ws/runs');
        assert.strictEqual(resolveOutputFolderSetting('/abs/runs/', '/ws', '/h'),
            '/abs/runs');
    });

    it('ignores a relative setting without a workspace', () => {
        assert.strictEqual(resolveOutputFolderSetting('runs', undefined, '/h'),
            undefined);
    });
});


describe('tokenizeCommand', () => {
    it('splits on whitespace like the old split(/\\s+/)', () => {
        assert.deepStrictEqual(tokenizeCommand('uv run gelbc'), ['uv', 'run', 'gelbc']);
        assert.deepStrictEqual(tokenizeCommand('  gelbc  '), ['gelbc']);
        assert.deepStrictEqual(tokenizeCommand('a\tb\nc'), ['a', 'b', 'c']);
    });

    it('returns no words for an empty or blank string', () => {
        assert.deepStrictEqual(tokenizeCommand(''), []);
        assert.deepStrictEqual(tokenizeCommand('   '), []);
    });

    it('groups single-quoted text literally', () => {
        assert.deepStrictEqual(
            tokenizeCommand("'/Users/me/My Tools/gelbc' --x"),
            ['/Users/me/My Tools/gelbc', '--x']);
        assert.deepStrictEqual(tokenizeCommand("'a\\\"b'"), ['a\\"b']);
    });

    it('groups double-quoted text with backslash escapes', () => {
        assert.deepStrictEqual(
            tokenizeCommand('"/Users/me/My Tools/gelb-view" source'),
            ['/Users/me/My Tools/gelb-view', 'source']);
        assert.deepStrictEqual(tokenizeCommand('"say \\"hi\\" \\\\ ok"'),
            ['say "hi" \\ ok']);
    });

    it('joins adjacent quoted and unquoted pieces', () => {
        assert.deepStrictEqual(tokenizeCommand('a"b c"d e'), ['ab cd', 'e']);
    });

    it('keeps an empty quoted word', () => {
        assert.deepStrictEqual(tokenizeCommand("x '' y"), ['x', '', 'y']);
    });

    it('keeps backslashes outside quotes', () => {
        assert.deepStrictEqual(tokenizeCommand('C:\\gelb\\gelbc.exe'),
            ['C:\\gelb\\gelbc.exe']);
    });

    it('keeps a backslash in double quotes unless it escapes " \\ $ `', () => {
        assert.deepStrictEqual(
            tokenizeCommand('"C:\\Program Files\\GeLB\\gelbc.exe" --x'),
            ['C:\\Program Files\\GeLB\\gelbc.exe', '--x']);
        assert.deepStrictEqual(tokenizeCommand('"\\$HOME \\` \\n"'),
            ['$HOME ` \\n']);
    });
});


describe('sourceCallsRandom', () => {
    it('finds a call', () => {
        assert.ok(sourceCallsRandom('f.out[x, y | 0] = (random() < 0.5) + 0;'));
        assert.ok(sourceCallsRandom('r = random ();'));
    });

    it('ignores a call in a line or block comment', () => {
        assert.ok(!sourceCallsRandom('// uses random() later\nx = 1;'));
        assert.ok(!sourceCallsRandom('/* random() */ x = 1;'));
    });

    it('ignores a string literal', () => {
        assert.ok(!sourceCallsRandom('simulation_description("random() ICs");'));
    });

    it('ignores identifiers that merely contain the word', () => {
        assert.ok(!sourceCallsRandom('x = randomize(1); y = my_random(2);'));
        assert.ok(!sourceCallsRandom('const real random_amp = 0.1;'));
    });
});


describe('runLensLine', () => {
    it('is the simulation_description line', () => {
        assert.strictEqual(runLensLine(
            '// header\n\nsimulation_description("x");\nglobal_constants {}'), 2);
    });

    it('skips a commented-out one', () => {
        assert.strictEqual(runLensLine(
            '/* simulation_description("old");\n*/\n  simulation_description ("x");'),
            2);
    });

    it('is 0 without one', () => {
        assert.strictEqual(runLensLine('global_constants {}'), 0);
    });
});
