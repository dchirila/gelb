/** Mocha inside the Extension Development Host; see ../runTests.js. */

const path = require('path');
const Mocha = require('mocha');

exports.run = function () {
    const mocha = new Mocha({ ui: 'bdd', timeout: 60000, color: false });
    for (const f of (process.env.GELB_SUITE_FILES || 'run.test.js').split(',')) {
        mocha.addFile(path.join(__dirname, f));
    }
    return new Promise((resolve, reject) => {
        mocha.run((failures) => (failures
            ? reject(new Error(`${failures} test(s) failed`)) : resolve()));
    });
};
