const assert = require('assert');
const vsctm = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');
const fs = require('fs');
const path = require('path');

// Load the WASM binary for Oniguruma
const wasmBin = fs.readFileSync(path.join(__dirname, '../node_modules/vscode-oniguruma/release/onig.wasm')).buffer;
const vscodeOnigurumaLib = oniguruma.loadWASM(wasmBin).then(() => {
    return {
        createOnigScanner(patterns) {
            return new oniguruma.OnigScanner(patterns);
        },
        createOnigString(s) {
            return new oniguruma.OnigString(s);
        }
    };
});

// Registry for loading grammars
const registry = new vsctm.Registry({
    onigLib: vscodeOnigurumaLib,
    loadGrammar: async (scopeName) => {
        if (scopeName === 'source.gelb') {
            const grammarPath = path.join(__dirname, '../syntaxes/gelb.tmLanguage.json');
            const grammarContent = fs.readFileSync(grammarPath, 'utf-8');
            return vsctm.parseRawGrammar(grammarContent, grammarPath);
        }
        return null;
    }
});

describe('GeLB Syntax Highlighting', () => {
    let grammar;

    before(async () => {
        grammar = await registry.loadGrammar('source.gelb');
    });

    /**
     * Helper function to tokenize a line and return scope names
     */
    function tokenizeLine(grammar, line) {
        const result = grammar.tokenizeLine(line, null);
        return result.tokens.map(token => ({
            text: line.substring(token.startIndex, token.endIndex),
            scopes: token.scopes
        }));
    }

    describe('Comments', () => {
        it('should highlight single-line comments', () => {
            const tokens = tokenizeLine(grammar, '// This is a comment');
            assert(tokens[0].scopes.includes('comment.line.double-slash.gelb'));
        });

        it('should highlight block comments', () => {
            const tokens = tokenizeLine(grammar, '/* This is a block comment */');
            assert(tokens.some(t => t.scopes.includes('comment.block.gelb')));
        });
    });

    describe('Keywords', () => {
        it('should highlight simulation_description keyword', () => {
            const tokens = tokenizeLine(grammar, 'simulation_description("test");');
            assert(tokens.some(t => 
                t.text === 'simulation_description' && 
                t.scopes.includes('keyword.control.gelb')
            ));
        });

        it('should highlight lattice declaration keyword', () => {
            const tokens = tokenizeLine(grammar, 'lattice f(d=2, q=9, df_type=real);');
            assert(tokens.some(t => 
                t.text === 'lattice' && 
                t.scopes.includes('keyword.control.gelb')
            ));
        });

        it('should highlight block keywords', () => {
            const blocks = ['global_constants', 'lattices', 'initializer', 'dynamic', 'gauge', 'node_classes', 'geometry'];
            blocks.forEach(block => {
                const tokens = tokenizeLine(grammar, `${block} {`);
                assert(tokens.some(t => 
                    t.text === block && 
                    t.scopes.includes('keyword.control.gelb')
                ), `Failed to highlight ${block}`);
            });
        });

        it('should highlight const keyword', () => {
            const tokens = tokenizeLine(grammar, 'const int N = 32;');
            assert(tokens.some(t => 
                t.text === 'const' && 
                t.scopes.includes('keyword.other.gelb')
            ));
        });

        it('should highlight in/out keywords', () => {
            const tokens = tokenizeLine(grammar, 'f.in[x,y|:] = f.out[x,y|:]');
            assert(tokens.some(t => t.text === 'in' && t.scopes.includes('keyword.other.gelb')));
            assert(tokens.some(t => t.text === 'out' && t.scopes.includes('keyword.other.gelb')));
        });
    });

    describe('Types', () => {
        it('should highlight int type', () => {
            const tokens = tokenizeLine(grammar, 'const int N = 32;');
            assert(tokens.some(t => 
                t.text === 'int' && 
                t.scopes.includes('storage.type.gelb')
            ));
        });

        it('should highlight real type', () => {
            const tokens = tokenizeLine(grammar, 'const real TAU = 0.6;');
            assert(tokens.some(t => 
                t.text === 'real' && 
                t.scopes.includes('storage.type.gelb')
            ));
        });

        it('should highlight bool type', () => {
            const tokens = tokenizeLine(grammar, 'bool flag = true;');
            assert(tokens.some(t => 
                t.text === 'bool' && 
                t.scopes.includes('storage.type.gelb')
            ));
        });
    });

    describe('Constants', () => {
        it('should highlight true/false', () => {
            const tokens = tokenizeLine(grammar, 'set_grid_periodicity({true, false});');
            assert(tokens.some(t => t.text === 'true' && t.scopes.includes('constant.language.gelb')));
            assert(tokens.some(t => t.text === 'false' && t.scopes.includes('constant.language.gelb')));
        });

        it('should highlight coordinate variables', () => {
            const coords = ['x', 'y', 'z'];
            coords.forEach(coord => {
                const tokens = tokenizeLine(grammar, `f.out[${coord}|:]`);
                assert(tokens.some(t => 
                    t.text === coord && 
                    t.scopes.includes('variable.language.coordinates.gelb')
                ), `Failed to highlight ${coord}`);
            });
        });
    });

    describe('Intrinsic Functions', () => {
        it('should highlight sum function', () => {
            const tokens = tokenizeLine(grammar, 'real rho = sum(f.in[x,y|:]);');
            assert(tokens.some(t => 
                t.text === 'sum' && 
                t.scopes.includes('support.function.builtin.gelb')
            ));
        });

        it('should highlight dot_prod function', () => {
            const tokens = tokenizeLine(grammar, 'real result = dot_prod(a, b);');
            assert(tokens.some(t => 
                t.text === 'dot_prod' && 
                t.scopes.includes('support.function.builtin.gelb')
            ));
        });
    });

    describe('Numbers', () => {
        it('should highlight integers', () => {
            const tokens = tokenizeLine(grammar, 'const int N = 128;');
            assert(tokens.some(t => 
                t.text === '128' && 
                t.scopes.includes('constant.numeric.integer.gelb')
            ));
        });

        it('should highlight floating point numbers', () => {
            const tokens = tokenizeLine(grammar, 'const real TAU = 0.6;');
            assert(tokens.some(t => 
                t.text === '0.6' && 
                t.scopes.includes('constant.numeric.float.gelb')
            ));
        });

        it('should highlight scientific notation', () => {
            const tokens = tokenizeLine(grammar, 'const real small = 1.0e-6;');
            assert(tokens.some(t => 
                t.text === '1.0e-6' && 
                t.scopes.includes('constant.numeric.float.gelb')
            ));
        });
    });

    describe('Strings', () => {
        it('should highlight string literals', () => {
            const tokens = tokenizeLine(grammar, 'simulation_description("Test simulation");');
            assert(tokens.some(t => 
                t.text.includes('"Test simulation"') && 
                t.scopes.includes('string.quoted.double.gelb')
            ));
        });
    });

    describe('Operators', () => {
        it('should highlight assignment operator', () => {
            const tokens = tokenizeLine(grammar, 'N = 32');
            assert(tokens.some(t => 
                t.text === '=' && 
                t.scopes.includes('keyword.operator.assignment.gelb')
            ));
        });

        it('should highlight arithmetic operators', () => {
            const operators = ['+', '-', '*', '/', '%', '^'];
            operators.forEach(op => {
                const tokens = tokenizeLine(grammar, `a ${op} b`);
                assert(tokens.some(t => 
                    t.text === op && 
                    t.scopes.includes('keyword.operator.arithmetic.gelb')
                ), `Failed to highlight ${op}`);
            });
        });

        it('should highlight comparison operators', () => {
            const operators = ['==', '!=', '<=', '>=', '<', '>'];
            operators.forEach(op => {
                const tokens = tokenizeLine(grammar, `a ${op} b`);
                assert(tokens.some(t => 
                    t.text === op && 
                    t.scopes.includes('keyword.operator.comparison.gelb')
                ), `Failed to highlight ${op}`);
            });
        });

        it('should highlight logical operators', () => {
            const tokens1 = tokenizeLine(grammar, 'a && b');
            assert(tokens1.some(t => t.text === '&&' && t.scopes.includes('keyword.operator.logical.gelb')));
            
            const tokens2 = tokenizeLine(grammar, 'a || b');
            assert(tokens2.some(t => t.text === '||' && t.scopes.includes('keyword.operator.logical.gelb')));
            
            const tokens3 = tokenizeLine(grammar, '!a');
            assert(tokens3.some(t => t.text === '!' && t.scopes.includes('keyword.operator.logical.gelb')));
        });
    });

    describe('Brackets and Punctuation', () => {
        it('should highlight array brackets', () => {
            const tokens = tokenizeLine(grammar, 'f.out[x,y|:]');
            assert(tokens.some(t => t.text === '[' && t.scopes.includes('punctuation.definition.array.gelb')));
            assert(tokens.some(t => t.text === ']' && t.scopes.includes('punctuation.definition.array.gelb')));
        });

        it('should highlight block braces', () => {
            const tokens = tokenizeLine(grammar, 'global_constants { }');
            assert(tokens.some(t => t.text === '{' && t.scopes.includes('punctuation.definition.block.gelb')));
            assert(tokens.some(t => t.text === '}' && t.scopes.includes('punctuation.definition.block.gelb')));
        });

        it('should highlight parentheses', () => {
            const tokens = tokenizeLine(grammar, 'sum(array)');
            assert(tokens.some(t => t.text === '(' && t.scopes.includes('punctuation.definition.parameters.gelb')));
            assert(tokens.some(t => t.text === ')' && t.scopes.includes('punctuation.definition.parameters.gelb')));
        });

        it('should highlight separators', () => {
            const tokens = tokenizeLine(grammar, 'f.out[x,y|:]');
            assert(tokens.some(t => t.text === ',' && t.scopes.includes('punctuation.separator.gelb')));
            assert(tokens.some(t => t.text === '|' && t.scopes.includes('punctuation.separator.gelb')));
            assert(tokens.some(t => t.text === ':' && t.scopes.includes('punctuation.separator.gelb')));
        });
    });

    describe('Complex Examples', () => {
        it('should correctly highlight a complete lattice declaration', () => {
            const line = 'lattice f(d=2, q=9, df_type=real);';
            const tokens = tokenizeLine(grammar, line);
            
            assert(tokens.some(t => t.text === 'lattice' && t.scopes.includes('keyword.control.gelb')));
            assert(tokens.some(t => t.text === 'real' && t.scopes.includes('storage.type.gelb')));
            assert(tokens.some(t => t.text === '2' && t.scopes.includes('constant.numeric.integer.gelb')));
            assert(tokens.some(t => t.text === '9' && t.scopes.includes('constant.numeric.integer.gelb')));
        });

        it('should correctly highlight a dynamic block statement', () => {
            const line = 'f.out[x,y|:] = f.in[x,y|:] + (1.0/TAU) * delta;';
            const tokens = tokenizeLine(grammar, line);
            
            assert(tokens.some(t => t.text === 'out' && t.scopes.includes('keyword.other.gelb')));
            assert(tokens.some(t => t.text === 'in' && t.scopes.includes('keyword.other.gelb')));
            assert(tokens.some(t => t.text === 'x' && t.scopes.includes('variable.language.coordinates.gelb')));
            assert(tokens.some(t => t.text === 'y' && t.scopes.includes('variable.language.coordinates.gelb')));
            assert(tokens.some(t => t.text === '1.0' && t.scopes.includes('constant.numeric.float.gelb')));
        });
    });
});