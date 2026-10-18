/**
 * "Program Structure" TreeView for the GeLB sidebar.
 *
 * Shows a GeLB-aware outline of the currently active .gelb file:
 * every top-level block (global_constants, lattices, initializer …,
 * dynamic …, gauge …, node_classes, geometry) and select nested
 * children (constants, lattice decls, node_class decls). Clicking
 * an item reveals its line in the editor.
 *
 * Parser is shared with the DocumentSymbolProvider and the
 * WorkspaceSymbolProvider (see gelbParser.ts) — this file only
 * translates the parser's output into the vscode.TreeView API.
 */

import * as vscode from 'vscode';

import { GelbSymbol, parseGelbSymbols } from './gelbParser';

/* ------------------------------------------------------------------ */
/*  Tree item                                                         */
/* ------------------------------------------------------------------ */

class GelbTreeItem extends vscode.TreeItem {
    constructor(
        public readonly symbol: GelbSymbol,
        public readonly uri: vscode.Uri,
    ) {
        const label = symbol.name;
        const state = symbol.children.length > 0
            ? vscode.TreeItemCollapsibleState.Expanded
            : vscode.TreeItemCollapsibleState.None;
        super(label, state);

        this.description = symbol.detail;
        this.iconPath = new vscode.ThemeIcon(iconIdForKind(symbol.kind));
        this.tooltip = this.buildTooltip();

        // Click → reveal the symbol in the editor. Use the built-in
        // vscode.open with a range so the command is native and
        // robust to background-buffer edits.
        const selRange = new vscode.Range(
            symbol.nameStartLine, symbol.nameStartCol,
            symbol.nameEndLine, symbol.nameEndCol,
        );
        this.command = {
            command: 'vscode.open',
            title: 'Go to',
            arguments: [
                uri,
                { selection: selRange, preserveFocus: false },
            ],
        };

        this.contextValue = `gelb.${symbol.kind}`;
    }

    private buildTooltip(): string {
        const parts: string[] = [this.symbol.kind];
        if (this.symbol.detail) parts.push(this.symbol.detail);
        parts.push(`line ${this.symbol.startLine + 1}`);
        return parts.join('\n');
    }
}

/* ------------------------------------------------------------------ */
/*  Tree data provider                                                */
/* ------------------------------------------------------------------ */

export class ProgramStructureProvider
    implements vscode.TreeDataProvider<GelbTreeItem>
{
    private _onDidChange = new vscode.EventEmitter<GelbTreeItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChange.event;

    private refreshTimer: NodeJS.Timeout | undefined;

    /** The .gelb document the sidebar is "pinned" to — set when the
     *  user focuses a .gelb editor OR when a preview command runs.
     *  Keeps the tree populated while a webview (preview) is focused,
     *  because `vscode.window.activeTextEditor` is undefined for
     *  webviews — without this, focusing the preview would blank the
     *  sidebar. */
    private currentDocument: vscode.TextDocument | undefined;

    getCurrentDocument(): vscode.TextDocument | undefined {
        return this.currentDocument;
    }

    /** Anchor the sidebar to `doc`. Pass `undefined` to clear. */
    setCurrentDocument(doc: vscode.TextDocument | undefined): void {
        if (doc && doc.languageId !== 'gelb') return;
        if (this.currentDocument?.uri.toString() === doc?.uri.toString()) {
            return;   // no-op, avoids superfluous refreshes
        }
        this.currentDocument = doc;
        this.refresh();
    }

    /** Ask VSCode to re-request the tree. Called by the extension
     *  host on editor changes / file saves / etc. */
    refresh(): void {
        this._onDidChange.fire(undefined);
    }

    /** Coalesced version for high-frequency events like onDidChangeTextDocument. */
    refreshDebounced(delayMs = 250): void {
        if (this.refreshTimer) clearTimeout(this.refreshTimer);
        this.refreshTimer = setTimeout(() => this.refresh(), delayMs);
    }

    getTreeItem(element: GelbTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: GelbTreeItem): vscode.ProviderResult<GelbTreeItem[]> {
        if (element) {
            return element.symbol.children.map(
                c => new GelbTreeItem(c, element.uri),
            );
        }

        // Top level: resolve the document to outline, with a precedence
        // chain that keeps the view meaningful when the webview is
        // focused. Order:
        //   1. active text editor, if it's a .gelb file — covers the
        //      common case of the user typing in the source.
        //   2. our sticky `currentDocument` — set by the preview
        //      commands and by any past .gelb-editor focus, so the
        //      outline survives focus on the preview webview.
        const ed = vscode.window.activeTextEditor;
        let doc: vscode.TextDocument | undefined;
        if (ed && ed.document.languageId === 'gelb') {
            doc = ed.document;
        } else {
            doc = this.currentDocument;
        }
        if (!doc) return [];

        const symbols = parseGelbSymbols(doc.getText());
        return symbols.map(s => new GelbTreeItem(s, doc.uri));
    }
}

/* ------------------------------------------------------------------ */
/*  Icon mapping                                                      */
/* ------------------------------------------------------------------ */

/**
 * Map a GeLB block kind to a VSCode codicon. Codicons are the
 * lightweight built-in glyph set; using them means the tree looks
 * correct in every theme without us shipping raster icons.
 *
 * Reference: https://microsoft.github.io/vscode-codicons/dist/codicon.html
 */
function iconIdForKind(kind: string): string {
    switch (kind) {
        case 'global_constants': return 'symbol-constant';
        case 'constant':         return 'symbol-constant';
        case 'lattices':         return 'layers';
        case 'lattice':          return 'symbol-struct';
        case 'function':         return 'symbol-function';
        case 'initializer':      return 'debug-start';
        case 'dynamic':          return 'sync';
        case 'gauge':            return 'dashboard';
        case 'node_classes':     return 'symbol-namespace';
        case 'node_class':       return 'symbol-class';
        case 'geometry':         return 'symbol-color';
        default:                 return 'symbol-misc';
    }
}
