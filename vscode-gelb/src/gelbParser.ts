/**
 * Lightweight structural parser for .gelb files.
 *
 * Produces a list of top-level blocks (global_constants, lattices,
 * initializer NAME, dynamic NAME, gauge NAME, function NAME,
 * node_classes, geometry) with nested children where meaningful
 * (constants inside global_constants; lattice declarations inside
 * lattices; node_class declarations inside node_classes).
 *
 * Used by three consumers:
 *   - the "Program Structure" TreeView (sidebar);
 *   - the DocumentSymbolProvider (Outline pane + breadcrumbs);
 *   - the WorkspaceSymbolProvider (Go to Symbol in Workspace, ⌘T).
 *
 * This is deliberately not a full parser: the compiler has its own
 * ANTLR4-based one. We only need enough structure to paint the
 * outline and jump to the right line; a brace counter + regex over
 * a comment-stripped source buffer is enough.
 */

export type GelbBlockKind =
    | 'global_constants'
    | 'constant'
    | 'lattices'
    | 'lattice'
    | 'function'
    | 'initializer'
    | 'dynamic'
    | 'gauge'
    | 'node_classes'
    | 'node_class'
    | 'geometry';

export interface GelbSymbol {
    /** Human-readable name. For anonymous container blocks
     *  (global_constants etc.) this is the keyword itself. */
    name: string;

    /** What kind of block this is. */
    kind: GelbBlockKind;

    /** Optional short description — e.g. the signature of a gauge
     *  or the `(init, dyn, gauge)` tuple of a node class. */
    detail?: string;

    /** Full range of the block, including the header and braces.
     *  All four numbers are 0-based. */
    startLine: number;
    startCol: number;
    endLine: number;
    endCol: number;

    /** Range of just the identifier (or the keyword, for
     *  anonymous containers). This is what Outline / breadcrumbs
     *  highlight when the user jumps to the symbol. */
    nameStartLine: number;
    nameStartCol: number;
    nameEndLine: number;
    nameEndCol: number;

    /** Nested sub-symbols (e.g. individual constants inside
     *  global_constants, node_class declarations inside
     *  node_classes). */
    children: GelbSymbol[];
}

/* ------------------------------------------------------------------ */
/*  Preprocessing: strip comments and string literals                 */
/* ------------------------------------------------------------------ */

/**
 * Replace every character inside a line comment, block comment, or
 * string literal with a space (newlines preserved). The resulting
 * buffer has identical length and line/column layout to the input,
 * so offsets computed on it map 1:1 back to the original source.
 */
export function stripCommentsAndStrings(source: string): string {
    const out: string[] = [];
    let i = 0;
    const n = source.length;

    while (i < n) {
        const c = source[i];
        const next = i + 1 < n ? source[i + 1] : '';

        // Line comment
        if (c === '/' && next === '/') {
            while (i < n && source[i] !== '\n') {
                out.push(' ');
                i++;
            }
            continue;
        }

        // Block comment
        if (c === '/' && next === '*') {
            out.push(' '); out.push(' ');
            i += 2;
            while (i < n) {
                if (source[i] === '*' && i + 1 < n && source[i + 1] === '/') {
                    out.push(' '); out.push(' ');
                    i += 2;
                    break;
                }
                out.push(source[i] === '\n' ? '\n' : ' ');
                i++;
            }
            continue;
        }

        // String literal (preserves braces inside it by blanking)
        if (c === '"') {
            out.push(' ');
            i++;
            while (i < n && source[i] !== '"') {
                if (source[i] === '\\' && i + 1 < n) {
                    out.push(' '); out.push(' ');
                    i += 2;
                    continue;
                }
                out.push(source[i] === '\n' ? '\n' : ' ');
                i++;
            }
            if (i < n) { out.push(' '); i++; }
            continue;
        }

        out.push(c);
        i++;
    }

    return out.join('');
}

/* ------------------------------------------------------------------ */
/*  Offset ↔ line/column bookkeeping                                  */
/* ------------------------------------------------------------------ */

/**
 * Build an array `lineStart[i]` = offset of the first character on
 * line i. Lets us convert any offset to a {line, col} pair in
 * O(log n) via binary search, O(1) for col.
 */
function buildLineIndex(source: string): number[] {
    const starts = [0];
    for (let i = 0; i < source.length; i++) {
        if (source[i] === '\n') starts.push(i + 1);
    }
    return starts;
}

function offsetToLineCol(starts: number[], offset: number): [number, number] {
    let lo = 0, hi = starts.length - 1;
    while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (starts[mid] <= offset) lo = mid;
        else hi = mid - 1;
    }
    return [lo, offset - starts[lo]];
}

/* ------------------------------------------------------------------ */
/*  Brace / paren matching                                            */
/* ------------------------------------------------------------------ */

/** Returns the offset of the `}` that closes the `{` at
 *  `openPos`, or -1 if the source is malformed. */
function findMatchingBrace(clean: string, openPos: number): number {
    let depth = 1;
    for (let i = openPos + 1; i < clean.length; i++) {
        if (clean[i] === '{') depth++;
        else if (clean[i] === '}') {
            depth--;
            if (depth === 0) return i;
        }
    }
    return -1;
}

function findMatchingParen(clean: string, openPos: number): number {
    let depth = 1;
    for (let i = openPos + 1; i < clean.length; i++) {
        if (clean[i] === '(') depth++;
        else if (clean[i] === ')') {
            depth--;
            if (depth === 0) return i;
        }
    }
    return -1;
}

/* ------------------------------------------------------------------ */
/*  Top-level block recognition                                       */
/* ------------------------------------------------------------------ */

/**
 * One recognition rule. For signature-bearing blocks the pattern ends
 * after the block name; the scanner then consumes the optional parameter
 * list and named-result clause before locating the body.
 */
interface BlockRule {
    kind: GelbBlockKind;
    /** /^(keyword)(\s+NAME)?(\s*\{)?/ */
    pattern: RegExp;
    /** Name capture-group index (0 = keyword itself, anonymous). */
    nameGroup: number;
    /** True if the block may carry a signature before its body. */
    hasSignature: boolean;
}

const TOP_LEVEL_RULES: BlockRule[] = [
    {
        kind: 'global_constants',
        pattern: /^global_constants\s*\{/,
        nameGroup: 0,
        hasSignature: false,
    },
    {
        kind: 'lattices',
        pattern: /^lattices\s*\{/,
        nameGroup: 0,
        hasSignature: false,
    },
    {
        kind: 'node_classes',
        pattern: /^node_classes\s*\{/,
        nameGroup: 0,
        hasSignature: false,
    },
    {
        kind: 'geometry',
        pattern: /^geometry\s*\{/,
        nameGroup: 0,
        hasSignature: false,
    },
    {
        kind: 'initializer',
        pattern: /^initializer\s+(\w+)\s*\{/,
        nameGroup: 1,
        hasSignature: false,
    },
    {
        kind: 'dynamic',
        pattern: /^dynamic\s+(\w+)\s*\{/,
        nameGroup: 1,
        hasSignature: false,
    },
    {
        kind: 'gauge',
        pattern: /^gauge\s+(\w+)/,
        nameGroup: 1,
        hasSignature: true,
    },
    {
        kind: 'function',
        pattern: /^function\s+(\w+)/,
        nameGroup: 1,
        hasSignature: true,
    },
];

/* ------------------------------------------------------------------ */
/*  Children inside container blocks                                  */
/* ------------------------------------------------------------------ */

/** const <type> <name> = ... ;  — captures type and name; the value
 *  runs from the `=` to the next `;`. */
const CONST_RE =
    /\bconst\s+(array\s*\[[^\]]+\]|\w+)\s+(\w+)\s*=/g;

/** lattice <name> ( ... ) ; */
const LATTICE_DECL_RE = /\blattice\s+(\w+)\s*\(/g;

/**
 * node_class <name> (<block list>) ;
 * node_class <name> ()                  — no blocks (masked, usually)
 * node_class <name> (<block list>) masked ;
 *
 * We capture the name and the block list so the outline entry can
 * show `(InitFoo, UpdateFoo, GaugeFoo)` as a detail.
 */
const NODE_CLASS_RE = /\bnode_class\s+(\w+)\s*\(([^)]*)\)/g;

/* ------------------------------------------------------------------ */
/*  Main entry point                                                  */
/* ------------------------------------------------------------------ */

export function parseGelbSymbols(source: string): GelbSymbol[] {
    const clean = stripCommentsAndStrings(source);
    const lineStarts = buildLineIndex(source);

    const out: GelbSymbol[] = [];

    let i = 0;
    const n = clean.length;
    let depth = 0;

    while (i < n) {
        // Match only at depth 0 and at a word boundary.
        if (depth === 0 && /[A-Za-z_]/.test(clean[i]) &&
            (i === 0 || !/[A-Za-z0-9_]/.test(clean[i - 1]))) {

            const rest = clean.slice(i);
            let matched = false;
            for (const rule of TOP_LEVEL_RULES) {
                const m = rest.match(rule.pattern);
                if (!m || m.index !== 0) continue;

                const headerLen = m[0].length;
                const keywordStart = i;
                const keywordEnd = i + rule.kind.length;   // exact length of the keyword
                let nameStart: number;
                let nameEnd: number;
                let nameText: string;
                let detail: string | undefined;

                if (rule.nameGroup === 0) {
                    nameStart = keywordStart;
                    nameEnd = keywordEnd;
                    nameText = rule.kind;
                } else {
                    const nameInHeader = m[rule.nameGroup];
                    // `m[rule.nameGroup]`'s offset inside `m[0]` is not
                    // given directly by JS regex, so re-locate it.
                    const relName = m[0].indexOf(nameInHeader, rule.kind.length);
                    nameStart = i + relName;
                    nameEnd = nameStart + nameInHeader.length;
                    nameText = nameInHeader;
                }

                // Figure out where the opening brace `{` is.
                let openBrace: number;
                if (!rule.hasSignature) {
                    // The header matched through to `{`. The last
                    // character of m[0] is the `{`.
                    openBrace = i + headerLen - 1;
                } else {
                    let j = i + headerLen;
                    while (j < n && /\s/.test(clean[j])) j++;

                    if (rule.kind === 'function') {
                        // Functions always have a parameter list, including
                        // the zero-input form `function F()`.
                        if (clean[j] !== '(') { i++; break; }
                        const openParams = j;
                        const closeParams =
                            findMatchingParen(clean, openParams);
                        if (closeParams < 0) { i++; break; }

                        j = closeParams + 1;
                        while (j < n && /\s/.test(clean[j])) j++;
                        if (clean.slice(j, j + 2) !== '->') { i++; break; }
                        j += 2;
                        while (j < n && /\s/.test(clean[j])) j++;
                        if (clean[j] !== '(') { i++; break; }
                        const openResults = j;
                        const closeResults =
                            findMatchingParen(clean, openResults);
                        if (closeResults < 0) { i++; break; }

                        detail = summariseSignature(
                            clean.slice(openParams, closeParams + 1),
                            clean.slice(openResults, closeResults + 1),
                        );
                        j = closeResults + 1;
                    } else if (clean.slice(j, j + 2) === '->') {
                        // A gauge has no parameter list. The entire arrow
                        // clause remains optional so compiler validation can
                        // issue the friendly missing-output diagnostic.
                        j += 2;
                        while (j < n && /\s/.test(clean[j])) j++;
                        if (clean[j] !== '(') { i++; break; }
                        const openResults = j;
                        const closeResults =
                            findMatchingParen(clean, openResults);
                        if (closeResults < 0) { i++; break; }
                        detail = summariseSignature(
                            undefined,
                            clean.slice(openResults, closeResults + 1),
                        );
                        j = closeResults + 1;
                    }

                    // No stray tokens may appear before the block body.
                    while (j < n && /\s/.test(clean[j])) j++;
                    if (clean[j] !== '{') { i++; break; }
                    openBrace = j;
                }

                const closeBrace = findMatchingBrace(clean, openBrace);
                if (closeBrace < 0) { i++; break; }

                const [sL, sC] = offsetToLineCol(lineStarts, keywordStart);
                const [eL, eC] = offsetToLineCol(lineStarts, closeBrace + 1);
                const [nsL, nsC] = offsetToLineCol(lineStarts, nameStart);
                const [neL, neC] = offsetToLineCol(lineStarts, nameEnd);

                const sym: GelbSymbol = {
                    name: nameText,
                    kind: rule.kind,
                    detail,
                    startLine: sL, startCol: sC,
                    endLine: eL, endCol: eC,
                    nameStartLine: nsL, nameStartCol: nsC,
                    nameEndLine: neL, nameEndCol: neC,
                    children: [],
                };

                // Children — only for the four container kinds.
                const bodyStart = openBrace + 1;
                const bodyEnd = closeBrace;
                if (rule.kind === 'global_constants') {
                    sym.children = collectConstants(
                        source, clean, bodyStart, bodyEnd, lineStarts);
                } else if (rule.kind === 'lattices') {
                    sym.children = collectLatticeDecls(
                        source, clean, bodyStart, bodyEnd, lineStarts);
                } else if (rule.kind === 'node_classes') {
                    sym.children = collectNodeClassDecls(
                        source, clean, bodyStart, bodyEnd, lineStarts);
                }

                out.push(sym);
                i = closeBrace + 1;
                matched = true;
                break;
            }

            if (matched) continue;
        }

        if (clean[i] === '{') depth++;
        else if (clean[i] === '}') depth--;
        i++;
    }

    return out;
}

/* ------------------------------------------------------------------ */
/*  Container-child collectors                                        */
/* ------------------------------------------------------------------ */

function collectConstants(
    source: string, clean: string,
    bodyStart: number, bodyEnd: number,
    lineStarts: number[],
): GelbSymbol[] {
    const out: GelbSymbol[] = [];
    const slice = clean.slice(bodyStart, bodyEnd);
    const re = new RegExp(CONST_RE.source, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(slice))) {
        const nameOff = bodyStart + m.index + m[0].lastIndexOf(m[2]);
        const [nsL, nsC] = offsetToLineCol(lineStarts, nameOff);
        const [neL, neC] = offsetToLineCol(lineStarts, nameOff + m[2].length);
        // `<type> = <value>` from the comment-stripped buffer, one line:
        // a multi-line array literal collapses to single spaces.
        const valueStart = bodyStart + m.index + m[0].length;
        let valueEnd = clean.indexOf(';', valueStart);
        if (valueEnd < 0 || valueEnd > bodyEnd) valueEnd = bodyEnd;
        const oneLine = (t: string) => t.replace(/\s+/g, ' ').trim();
        const value = oneLine(clean.slice(valueStart, valueEnd));
        out.push({
            name: m[2], kind: 'constant',
            detail: `${oneLine(m[1])} = ${value}`,
            startLine: nsL, startCol: nsC,
            endLine: neL, endCol: neC,
            nameStartLine: nsL, nameStartCol: nsC,
            nameEndLine: neL, nameEndCol: neC,
            children: [],
        });
    }
    return out;
}

function collectLatticeDecls(
    source: string, clean: string,
    bodyStart: number, bodyEnd: number,
    lineStarts: number[],
): GelbSymbol[] {
    const out: GelbSymbol[] = [];
    const slice = clean.slice(bodyStart, bodyEnd);
    const re = new RegExp(LATTICE_DECL_RE.source, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(slice))) {
        const absOpenParen = bodyStart + m.index + m[0].length - 1;
        const closeParen = findMatchingParen(clean, absOpenParen);
        if (closeParen < 0) continue;
        const nameOff = bodyStart + m.index + m[0].indexOf(m[1]);
        const [sL, sC] = offsetToLineCol(lineStarts, bodyStart + m.index);
        const [eL, eC] = offsetToLineCol(lineStarts, closeParen + 1);
        const [nsL, nsC] = offsetToLineCol(lineStarts, nameOff);
        const [neL, neC] = offsetToLineCol(lineStarts, nameOff + m[1].length);
        const sig = source.slice(absOpenParen, closeParen + 1);
        out.push({
            name: m[1], kind: 'lattice',
            detail: summariseLatticeSig(sig),
            startLine: sL, startCol: sC,
            endLine: eL, endCol: eC,
            nameStartLine: nsL, nameStartCol: nsC,
            nameEndLine: neL, nameEndCol: neC,
            children: [],
        });
    }
    return out;
}

function collectNodeClassDecls(
    source: string, clean: string,
    bodyStart: number, bodyEnd: number,
    lineStarts: number[],
): GelbSymbol[] {
    const out: GelbSymbol[] = [];
    const slice = clean.slice(bodyStart, bodyEnd);
    const re = new RegExp(NODE_CLASS_RE.source, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(slice))) {
        const absStart = bodyStart + m.index;
        const absEnd   = absStart + m[0].length;
        const nameOff = absStart + m[0].indexOf(m[1]);
        const [sL, sC] = offsetToLineCol(lineStarts, absStart);
        const [eL, eC] = offsetToLineCol(lineStarts, absEnd);
        const [nsL, nsC] = offsetToLineCol(lineStarts, nameOff);
        const [neL, neC] = offsetToLineCol(lineStarts, nameOff + m[1].length);

        // m[2] is the block list (may be empty). Detect trailing
        // "masked" marker after the closing paren.
        const blockList = m[2].trim();
        const tail = source.slice(absEnd, Math.min(absEnd + 20, bodyEnd));
        const isMasked = /^\s*masked\b/.test(tail);

        let detail: string;
        if (isMasked) {
            detail = blockList.length > 0
                ? `(${blockList}) masked`
                : '() masked';
        } else {
            detail = blockList.length > 0 ? `(${blockList})` : '()';
        }

        out.push({
            name: m[1], kind: 'node_class', detail,
            startLine: sL, startCol: sC,
            endLine: eL, endCol: eC,
            nameStartLine: nsL, nameStartCol: nsC,
            nameEndLine: neL, nameEndCol: neC,
            children: [],
        });
    }
    return out;
}

/* ------------------------------------------------------------------ */
/*  Signature summarisation                                            */
/* ------------------------------------------------------------------ */

/** Split a comma-separated list while respecting nested type delimiters. */
function splitTopLevelList(body: string): string[] {
    const parts: string[] = [];
    let depth = 0;
    let current = '';
    for (const char of body) {
        if (char === '(' || char === '{' || char === '[') depth++;
        else if (char === ')' || char === '}' || char === ']') depth--;
        if (char === ',' && depth === 0) {
            parts.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    if (current.trim()) parts.push(current.trim());
    return parts;
}

/**
 * Compress a canonical function or gauge signature to an outline detail.
 *   "(array[real, 9] fIn) -> (real rho, real ux)"
 *     → "(fIn → rho, ux)"
 */
function summariseSignature(
    inputs: string | undefined,
    results: string,
): string {
    const names = (list: string): string[] => {
        const body = list.replace(/^\(|\)$/g, '').trim();
        if (!body) return [];
        return splitTopLevelList(body)
            .map(param => param.match(/([A-Za-z_]\w*)\s*$/)?.[1])
            .filter((name): name is string => name !== undefined);
    };

    const ins = inputs === undefined ? [] : names(inputs);
    const outs = names(results);

    if (ins.length === 0) return `(→ ${outs.join(', ')})`;
    if (outs.length === 0) return `(${ins.join(', ')} →)`;
    return `(${ins.join(', ')} → ${outs.join(', ')})`;
}

/**
 * Compress a `lattice(...)` signature:
 *   "(2, 9, real, {NX, NY}, {true, false})"
 *     →  "d=2, q=9, real"
 *
 * Only the first three args are distinctive enough to show in a
 * compact outline detail.
 */
function summariseLatticeSig(sig: string): string {
    const body = sig.replace(/^\(|\)$/g, '').trim();
    const parts = splitTopLevelList(body);
    const d = parts[0] ?? '?';
    const q = parts[1] ?? '?';
    const t = parts[2] ?? '?';
    return `d=${d}, q=${q}, ${t}`;
}
