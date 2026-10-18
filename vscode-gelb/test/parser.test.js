const assert = require('assert');

const { parseGelbSymbols } = require('../out/gelbParser');


function symbolFrom(source) {
    const symbols = parseGelbSymbols(source);
    assert.strictEqual(symbols.length, 1);
    return symbols[0];
}


describe('GeLB structural parser signatures', () => {
    it('finds a function with parameters and named results', () => {
        const symbol = symbolFrom(
            'function Macro(array[real, 9] fIn, real scale) ' +
            '-> (real rho, real ux) { rho = scale; ux = scale; }'
        );

        assert.strictEqual(symbol.kind, 'function');
        assert.strictEqual(symbol.name, 'Macro');
        assert.strictEqual(symbol.detail, '(fIn, scale → rho, ux)');
    });

    it('finds a zero-input function', () => {
        const symbol = symbolFrom(
            'function Noise() -> (real value) { value = 1.0; }'
        );

        assert.strictEqual(symbol.kind, 'function');
        assert.strictEqual(symbol.name, 'Noise');
        assert.strictEqual(symbol.detail, '(→ value)');
    });

    it('finds a gauge without a parameter list', () => {
        const symbol = symbolFrom(
            'gauge Hydro -> (real rho, real ux) { rho = 1.0; ux = 0.0; }'
        );

        assert.strictEqual(symbol.kind, 'gauge');
        assert.strictEqual(symbol.name, 'Hydro');
        assert.strictEqual(symbol.detail, '(→ rho, ux)');
    });

    it('finds and summarises a multiline signature', () => {
        const symbol = symbolFrom(`
function Analyse(
    array[real, {3, 3}] matrix,
    real scale
)
        -> (
            real result,
            int count
        ) {
    result = scale;
    count = 3;
}`);

        assert.strictEqual(symbol.kind, 'function');
        assert.strictEqual(symbol.name, 'Analyse');
        assert.strictEqual(
            symbol.detail,
            '(matrix, scale → result, count)'
        );
    });
});


describe('GeLB structural parser constants', () => {
    it('gives each constant a "<type> = <value>" detail', () => {
        const symbol = symbolFrom(`
global_constants {
    const int N = 65;
    const real TAU_INV = 1.0 / TAU;   // derived
    const array[real, 3] W = {4.0/9.0,
        1.0/9.0,   /* axis */
        1.0/36.0};
}`);

        assert.strictEqual(symbol.kind, 'global_constants');
        assert.deepStrictEqual(
            symbol.children.map(c => [c.kind, c.name, c.detail]),
            [
                ['constant', 'N', 'int = 65'],
                ['constant', 'TAU_INV', 'real = 1.0 / TAU'],
                ['constant', 'W', 'array[real, 3] = {4.0/9.0, 1.0/9.0, 1.0/36.0}'],
            ]);
    });
});
