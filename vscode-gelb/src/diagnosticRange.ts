/**
 * gelbc's --diagnostics-json gives a position rather than a span: its
 * ranges are one character wide (the start of the offending name or
 * token). VS Code would underline just that character; the extension
 * underlines the whole word starting there instead.
 *
 * No `vscode` import here, so mocha can test this module from `out/`.
 */

/** The squiggle's columns on `line` for gelbc's range [start, end):
 *  a range of at most one character on the start of a word (a GeLB
 *  name or a number) grows to the end of that word; anything else is
 *  kept as it is. */
export function widenToWord(line: string, start: number, end: number): [number, number] {
    if (end - start > 1 || start < 0 || start >= line.length) return [start, end];
    const m = /^[A-Za-z_][A-Za-z0-9_]*|^[0-9][0-9.]*(?:[eE][+-]?[0-9]+)?/.exec(line.slice(start));
    return m ? [start, start + m[0].length] : [start, end];
}
