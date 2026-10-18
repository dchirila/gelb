const assert = require('assert');

const { widenToWord } = require('../out/diagnosticRange');


describe('widenToWord', () => {
    const line = '    nodes[:, N - 1] = LDI;     // top lid';

    it('grows a one-character range at a name to the whole name', () => {
        assert.deepStrictEqual(widenToWord(line, 22, 23), [22, 25]);
    });

    it('grows an empty range too', () => {
        assert.deepStrictEqual(widenToWord(line, 22, 22), [22, 25]);
    });

    it('takes underscores and digits as part of a name', () => {
        assert.deepStrictEqual(widenToWord('x = TAU_INV2 * y', 4, 5), [4, 12]);
    });

    it('takes a number with its exponent, not the operator after it', () => {
        assert.deepStrictEqual(widenToWord('a = 1.5e-3-b', 4, 5), [4, 10]);
    });

    it('keeps a range that already spans more than one character', () => {
        assert.deepStrictEqual(widenToWord(line, 22, 24), [22, 24]);
    });

    it('keeps a range on punctuation or past the end of the line', () => {
        assert.deepStrictEqual(widenToWord(line, 25, 26), [25, 26]);
        assert.deepStrictEqual(widenToWord(line, 99, 100), [99, 100]);
    });
});
