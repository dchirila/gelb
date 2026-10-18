/**
 * Document- and workspace-level SymbolProviders for GeLB.
 *
 *   - GelbDocumentSymbolProvider feeds the built-in Outline pane
 *     and the breadcrumb bar, plus the "Go to Symbol in Editor"
 *     picker (⌘⇧O / Ctrl+Shift+O).
 *   - GelbWorkspaceSymbolProvider feeds the "Go to Symbol in
 *     Workspace" picker (⌘T / Ctrl+T).
 *
 * Both reuse parseGelbSymbols() from gelbParser.ts — the same
 * structural parser that powers the sidebar tree view. That way
 * any time we teach the parser a new block form (say, a future
 * `macro` keyword), all three surfaces update in lockstep.
 */

import * as vscode from 'vscode';

import { GelbSymbol, parseGelbSymbols } from './gelbParser';

/* ------------------------------------------------------------------ */
/*  Document symbols                                                  */
/* ------------------------------------------------------------------ */

export class GelbDocumentSymbolProvider
    implements vscode.DocumentSymbolProvider
{
    provideDocumentSymbols(
        document: vscode.TextDocument,
        _token: vscode.CancellationToken,
    ): vscode.ProviderResult<vscode.DocumentSymbol[]> {
        const symbols = parseGelbSymbols(document.getText());
        return symbols.map(s => toDocumentSymbol(s));
    }
}

function toDocumentSymbol(sym: GelbSymbol): vscode.DocumentSymbol {
    const range = new vscode.Range(
        sym.startLine, sym.startCol,
        sym.endLine, sym.endCol,
    );
    const selRange = new vscode.Range(
        sym.nameStartLine, sym.nameStartCol,
        sym.nameEndLine, sym.nameEndCol,
    );
    const ds = new vscode.DocumentSymbol(
        sym.name,
        sym.detail ?? vscodeKindLabel(sym.kind),
        vscodeKind(sym.kind),
        range,
        selRange,
    );
    ds.children = sym.children.map(c => toDocumentSymbol(c));
    return ds;
}

/* ------------------------------------------------------------------ */
/*  Workspace symbols                                                 */
/* ------------------------------------------------------------------ */

export class GelbWorkspaceSymbolProvider
    implements vscode.WorkspaceSymbolProvider
{
    async provideWorkspaceSymbols(
        query: string,
        token: vscode.CancellationToken,
    ): Promise<vscode.SymbolInformation[]> {
        // Scan every .gelb file that isn't in node_modules or .git.
        // `findFiles` respects files.exclude so build artefacts etc.
        // are already filtered out.
        const uris = await vscode.workspace.findFiles(
            '**/*.gelb',
            '**/node_modules/**',
        );

        const q = query.toLowerCase();
        const results: vscode.SymbolInformation[] = [];

        for (const uri of uris) {
            if (token.isCancellationRequested) return results;
            let doc: vscode.TextDocument;
            try {
                doc = await vscode.workspace.openTextDocument(uri);
            } catch {
                continue;
            }
            const tree = parseGelbSymbols(doc.getText());
            collectWorkspaceSymbols(tree, uri, q, results, '');
        }

        return results;
    }
}

function collectWorkspaceSymbols(
    symbols: GelbSymbol[],
    uri: vscode.Uri,
    query: string,
    out: vscode.SymbolInformation[],
    container: string,
): void {
    for (const sym of symbols) {
        const matches = query.length === 0 ||
            sym.name.toLowerCase().includes(query);
        if (matches) {
            const range = new vscode.Range(
                sym.nameStartLine, sym.nameStartCol,
                sym.nameEndLine, sym.nameEndCol,
            );
            out.push(new vscode.SymbolInformation(
                sym.name,
                vscodeKind(sym.kind),
                container,
                new vscode.Location(uri, range),
            ));
        }
        if (sym.children.length > 0) {
            const nextContainer = container.length > 0
                ? `${container}.${sym.name}`
                : sym.name;
            collectWorkspaceSymbols(
                sym.children, uri, query, out, nextContainer,
            );
        }
    }
}

/* ------------------------------------------------------------------ */
/*  Kind mapping                                                      */
/* ------------------------------------------------------------------ */

/**
 * Map a GeLB block kind to a vscode.SymbolKind. The VSCode enum
 * is a fixed set (Class, Method, Function, Namespace, Struct …),
 * so we approximate:
 *   initializer / dynamic / gauge  → Method    (per-cell phase)
 *   function                       → Function
 *   node_class                     → Class     (behaviour binding)
 *   lattice                        → Struct    (data-layout decl)
 *   constant                       → Constant
 *   global_constants / node_classes / lattices / geometry
 *                                   → Namespace (container-y)
 */
function vscodeKind(kind: string): vscode.SymbolKind {
    switch (kind) {
        case 'global_constants':
        case 'lattices':
        case 'node_classes':
        case 'geometry':
            return vscode.SymbolKind.Namespace;
        case 'constant':     return vscode.SymbolKind.Constant;
        case 'lattice':      return vscode.SymbolKind.Struct;
        case 'function':     return vscode.SymbolKind.Function;
        case 'initializer':
        case 'dynamic':
        case 'gauge':
            return vscode.SymbolKind.Method;
        case 'node_class':   return vscode.SymbolKind.Class;
        default:             return vscode.SymbolKind.Object;
    }
}

function vscodeKindLabel(kind: string): string {
    switch (kind) {
        case 'initializer': return 'initializer block';
        case 'dynamic':     return 'dynamic block';
        case 'gauge':       return 'gauge block';
        case 'function':    return 'user function';
        case 'node_class':  return 'node class';
        case 'lattice':     return 'lattice';
        case 'constant':    return 'const';
        default:            return kind;
    }
}
