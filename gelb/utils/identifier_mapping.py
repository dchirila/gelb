#!/usr/bin/env python3
"""
GeLB -> Fortran identifier mapping.

Provides structured data about how user-written GeLB identifiers map
to Fortran identifiers in the generated code.  Used by ``gelbc
--show-mapping`` and potentially by IDE tooling (e.g. the VSCode
extension) for go-to-definition and hover tooltips.
"""

from gelb.backends.stage3_backend_cpu_fortran_serial import FortranCodeGenerator
from gelb.frontend.implicit_symbols import (
    active_coordinate_names,
    active_dimension_names,
    dimensionality_from_program,
)
from gelb.gelb_ast.ASTNodes import (
    ConstantDefinitionStmt_N, VariableDeclarationStmt_N,
    LatticeInstaStmt_N, List_N
)

# Re-export the encoding function for external consumers
uname = FortranCodeGenerator._uname


def _is_user_written(name):
    """Filter out compiler-generated names from function inlining."""
    return not name.startswith('__')


def _collect_block_locals(block, encode=uname):
    """Collect user-written constants and variables declared in a block."""
    entries = []
    for stmt in block.stmts:
        if isinstance(stmt, ConstantDefinitionStmt_N):
            name = stmt.name.name
            if _is_user_written(name):
                entries.append((name, encode(name)))
        elif isinstance(stmt, VariableDeclarationStmt_N):
            name = stmt.name.name
            if _is_user_written(name):
                entries.append((name, encode(name)))
    return entries


def collect_identifier_mapping(ast):
    """Collect all user-written GeLB -> Fortran identifier mappings.

    Returns a list of sections, each being a dict with:
      - ``title``: section heading (e.g. "Global constants")
      - ``entries``: list of ``(gelb_name, fortran_name)`` tuples
    """
    sections = []
    # Use the backend's scope allocation so --show-mapping agrees with
    # block-qualified declarations, including bounded long identifiers.
    generator = FortranCodeGenerator(ast)
    generator._collect_variables(generator._resolve_geometry_via_midware())

    def local_encoder(block):
        names = generator._local_names.get(id(block), {})
        return lambda name: names.get(name) or generator._symbol_name(name)

    # --- Implicit symbols ---
    implicit_entries = []
    dimensionality = dimensionality_from_program(ast)
    for coord_name, dim_name in zip(
        active_coordinate_names(dimensionality),
        active_dimension_names(dimensionality),
    ):
        implicit_entries.append((coord_name, uname(coord_name)))
        implicit_entries.append((dim_name, uname(dim_name)))
    if implicit_entries:
        sections.append({'title': 'Implicit symbols', 'entries': implicit_entries})

    # --- Global constants ---
    if ast.global_constants:
        entries = []
        for stmt in ast.global_constants.stmts:
            if isinstance(stmt, ConstantDefinitionStmt_N):
                name = stmt.name.name
                entries.append((name, uname(name)))
        if entries:
            sections.append({'title': 'Global constants', 'entries': entries})

    # --- Lattices ---
    if ast.lattices:
        entries = []
        for stmt in ast.lattices.stmts.elements:
            if isinstance(stmt, LatticeInstaStmt_N):
                name = stmt.name.name
                entries.append((name, uname(name)))
        if entries:
            sections.append({'title': 'Lattices', 'entries': entries})

    # --- User-defined functions ---
    functions = ast.functions
    if functions:
        if isinstance(functions, List_N):
            functions = functions.elements
        for func in functions:
            entries = []
            for param in func.inputs.elements:
                entries.append((param.name.name, uname(param.name.name)))
            for param in func.outputs.elements:
                entries.append((param.name.name, uname(param.name.name)))
            entries.extend(_collect_block_locals(func))
            if entries:
                sections.append({
                    'title': f'Function {func.name.name} ({uname(func.name.name)})',
                    'entries': entries,
                })

    # --- Initializers ---
    for block in ast.initializers:
        entries = _collect_block_locals(block, local_encoder(block))
        if entries:
            sections.append({
                'title': f'Initializer {block.name.name}',
                'entries': entries,
            })

    # --- Dynamics ---
    for block in ast.dynamics:
        entries = _collect_block_locals(block, local_encoder(block))
        if entries:
            sections.append({
                'title': f'Dynamic {block.name.name}',
                'entries': entries,
            })

    # --- Gauges ---
    for gauge in ast.gauges:
        entries = []
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                name = decl.name.name
                entries.append((name, local_encoder(gauge)(name)))
        entries.extend(_collect_block_locals(gauge, local_encoder(gauge)))
        if entries:
            sections.append({
                'title': f'Gauge {gauge.name.name}',
                'entries': entries,
            })

    return sections


def format_identifier_mapping(sections):
    """Format mapping sections as a human-readable string."""
    lines = []
    for section in sections:
        entries = section['entries']
        if not entries:
            continue
        max_gelb = max(max(len(g) for g, _ in entries), len('GeLB'))
        max_fort = max(max(len(f) for _, f in entries), len('Fortran'))
        lines.append(f'\n{section["title"]}')
        lines.append(f'  {"GeLB":<{max_gelb}}  {"Fortran":<{max_fort}}')
        lines.append(f'  {"─" * max_gelb}  {"─" * max_fort}')
        for gelb_name, fort_name in entries:
            lines.append(f'  {gelb_name:<{max_gelb}}  {fort_name:<{max_fort}}')
    return '\n'.join(lines)
