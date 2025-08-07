/**
 * Simple grammar tests that can run with Node.js directly
 * Run with: node test/grammar.test.js
 */

const fs = require('fs');
const path = require('path');

// Load and validate the grammar file
const grammarPath = path.join(__dirname, '../syntaxes/gelb.tmLanguage.json');
const grammarContent = fs.readFileSync(grammarPath, 'utf-8');
const grammar = JSON.parse(grammarContent);

let testsPassed = 0;
let testsFailed = 0;

function assert(condition, message) {
    if (condition) {
        console.log(`✓ ${message}`);
        testsPassed++;
    } else {
        console.error(`✗ ${message}`);
        testsFailed++;
    }
}

console.log('Testing GeLB TextMate Grammar Structure...\n');

// Test basic structure
assert(grammar.$schema, 'Grammar has $schema property');
assert(grammar.name === 'GeLB', 'Grammar name is GeLB');
assert(grammar.scopeName === 'source.gelb', 'Scope name is source.gelb');
assert(Array.isArray(grammar.patterns), 'Grammar has patterns array');
assert(grammar.repository, 'Grammar has repository');

// Test repository sections
const requiredSections = [
    'comments', 'strings', 'keywords', 'types', 
    'constants', 'intrinsic-functions', 'operators', 
    'numbers', 'identifiers'
];

requiredSections.forEach(section => {
    assert(grammar.repository[section], `Repository has ${section} section`);
});

// Test keyword patterns
const keywords = grammar.repository.keywords.patterns;
assert(keywords.length > 0, 'Keywords section has patterns');

const expectedKeywords = [
    'simulation_description', 'global_constants', 'lattices', 
    'lattice', 'initializer', 'dynamic', 'gauge', 
    'node_classes', 'node_class', 'geometry', 'nodes'
];

const keywordPattern = keywords.find(p => p.name === 'keyword.control.gelb');
assert(keywordPattern, 'Has keyword.control.gelb pattern');

if (keywordPattern) {
    expectedKeywords.forEach(kw => {
        const regex = new RegExp(keywordPattern.match);
        assert(regex.test(` ${kw} `), `Keyword pattern matches '${kw}'`);
    });
}

// Test type patterns
const types = grammar.repository.types.patterns;
assert(types.length > 0, 'Types section has patterns');

const expectedTypes = ['int', 'real', 'bool'];
const typePattern = types.find(p => p.name === 'storage.type.gelb');
assert(typePattern, 'Has storage.type.gelb pattern');

if (typePattern) {
    expectedTypes.forEach(type => {
        const regex = new RegExp(typePattern.match);
        assert(regex.test(` ${type} `), `Type pattern matches '${type}'`);
    });
}

// Test intrinsic functions
const intrinsics = grammar.repository['intrinsic-functions'].patterns;
assert(intrinsics.length > 0, 'Intrinsic functions section has patterns');

const expectedFunctions = ['sum', 'dot_prod'];
const functionPattern = intrinsics.find(p => p.name === 'support.function.builtin.gelb');
assert(functionPattern, 'Has support.function.builtin.gelb pattern');

if (functionPattern) {
    expectedFunctions.forEach(func => {
        const regex = new RegExp(functionPattern.match);
        assert(regex.test(` ${func} `), `Function pattern matches '${func}'`);
    });
}

// Test comment patterns
const comments = grammar.repository.comments.patterns;
assert(comments.length === 2, 'Has both line and block comment patterns');
assert(comments.some(c => c.name === 'comment.line.double-slash.gelb'), 'Has line comment pattern');
assert(comments.some(c => c.name === 'comment.block.gelb'), 'Has block comment pattern');

// Test number patterns
const numbers = grammar.repository.numbers.patterns;
assert(numbers.length >= 2, 'Has patterns for integers and floats');
assert(numbers.some(n => n.name === 'constant.numeric.integer.gelb'), 'Has integer pattern');
assert(numbers.some(n => n.name === 'constant.numeric.float.gelb'), 'Has float pattern');

// Test operator patterns
const operators = grammar.repository.operators.patterns;
assert(operators.some(o => o.name === 'keyword.operator.assignment.gelb'), 'Has assignment operator');
assert(operators.some(o => o.name === 'keyword.operator.arithmetic.gelb'), 'Has arithmetic operators');
assert(operators.some(o => o.name === 'keyword.operator.comparison.gelb'), 'Has comparison operators');
assert(operators.some(o => o.name === 'keyword.operator.logical.gelb'), 'Has logical operators');

// Summary
console.log('\n' + '='.repeat(50));
console.log(`Tests passed: ${testsPassed}`);
console.log(`Tests failed: ${testsFailed}`);
console.log('='.repeat(50));

if (testsFailed > 0) {
    process.exit(1);
} else {
    console.log('\n✅ All grammar structure tests passed!');
}