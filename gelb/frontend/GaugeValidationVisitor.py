#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend import type_rules
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError


class GaugeValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for validating function and gauge signatures.

    Validates that:
    1. All functions declare at least one named result
    2. All gauges have non-empty output specifications
    3. All gauge outputs are assigned in the gauge body
    4. Gauges that declare an output of the same name give it one type
    """

    # ``int64`` is ``int`` and ``real64`` is ``real`` (type_rules): one
    # type, one output buffer and one NetCDF type on every backend.
    _SAME_TYPE = {'int64': 'int', 'real64': 'real'}
    
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        if node.functions is not None:
            for function in node.functions:
                self.visit(function, ast_root_node)

        if hasattr(node, 'gauges') and node.gauges:
            for gauge in node.gauges:
                self.visit(gauge, ast_root_node)
            self._validate_shared_output_types(node.gauges)
        return node

    def visitFunctionBlock_N(
            self,
            node: FunctionBlock_N,
            ast_root_node: Program_N
    ):
        if len(node.outputs.elements) == 0:
            raise GeLBExTypeError(
                node,
                f"Function '{node.name.name}' has no results",
                "Functions must declare at least one named result using "
                "'-> (type name, ...)'. A function with one result is used "
                "as an expression; a function with several results is used "
                "with destructuring assignment."
            )
        return node

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N,
            ast_root_node: Program_N
    ):
        # Check if outputs list is empty (no output specification)
        if len(node.outputs.elements) == 0:
            raise GeLBExTypeError(
                node,
                f"Gauge '{node.name.name}' has no output specification",
                "Gauges must specify at least one named result using "
                "'-> (type name, ...)'. "
                f"For example: 'gauge {node.name.name} "
                "-> (int result) { ... }'"
            )
        
        # Check if all output declarations are valid
        for output in node.outputs.elements:
            if not isinstance(output, VariableDeclarationStmt_N):
                raise GeLBExTypeError(
                    output,
                    f"Invalid output specification in gauge '{node.name.name}'",
                    "Gauge outputs must be variable declarations like 'int var;' or 'real result;'"
                )
            # A gauge output is one scalar per cell, one field in the
            # output file.  An array output passed the frontend and
            # reached the backends, whose output buffers have only the
            # spatial dimensions: not in this version (user manual,
            # Numerical semantics: Not in this version), said here.
            if self._is_array_type(output.data_type):
                raise GeLBExTypeError(
                    output,
                    f"Gauge '{node.name.name}' output '{output.name.name}' "
                    "is an array",
                    "A gauge output is one scalar per cell, written to the "
                    "output file as one field; an array-valued output is "
                    "not in this version.  Declare one scalar output per "
                    f"component, for example '-> (real {output.name.name}0, "
                    f"real {output.name.name}1)', and assign each."
                )
        
        # Check that all declared output variables are assigned in the gauge body
        self._validate_output_assignments(node)
        
        return node
    
    def _validate_shared_output_types(self, gauges):
        """Gauges share an output by its name: one field of the output
        file (user manual, GeLB in 10 minutes: Node classes and
        geometry).  So every gauge that declares an output of a given
        name must give it the same type, whether a node class uses the
        gauge or not."""
        # A gauge name used twice, or an output name repeated in one
        # gauge, is the symbol table's to report (build_symbols_tables
        # rejects both); comparing types first would hide that error.
        gauge_names = [gauge.name.name for gauge in gauges]
        if len(set(gauge_names)) != len(gauge_names) or any(
                len({output.name.name for output in gauge.outputs.elements})
                != len(gauge.outputs.elements) for gauge in gauges):
            return
        first = {}
        for gauge in gauges:
            for output in gauge.outputs.elements:
                name = output.name.name
                dtype = output.data_type.element_dtype
                other, other_dtype = first.setdefault(name, (gauge, dtype))
                if (self._SAME_TYPE.get(dtype, dtype)
                        != self._SAME_TYPE.get(other_dtype, other_dtype)):
                    raise GeLBExTypeError(
                        output,
                        f"Gauge '{gauge.name.name}' declares output '{name}' "
                        f"as {dtype}, but gauge '{other.name.name}' declares "
                        f"it as {other_dtype}",
                        "Gauges share an output by its name (one field of the "
                        f"output file), so every gauge that declares '{name}' "
                        "must give it the same type, whether a node class "
                        "uses the gauge or not. Declare it as "
                        f"{type_rules.common_type(dtype, other_dtype)} in "
                        "both gauges, or give one of the two outputs another "
                        "name."
                    )

    @staticmethod
    def _is_array_type(data_type):
        """True for a declared array type with at least one extent (a
        scalar is an ``ArrayDataType_N`` with an empty shape list)."""
        if not isinstance(data_type, ArrayDataType_N):
            return False
        shape = data_type.shape
        return not (isinstance(shape, List_N) and len(shape.elements) == 0)

    def _validate_output_assignments(self, gauge_node: GaugeBlock_N):
        """
        Validate that all declared output variables are assigned within the gauge body.
        """
        # Collect all declared output variable names
        declared_outputs = set()
        for output_decl in gauge_node.outputs.elements:
            if isinstance(output_decl, VariableDeclarationStmt_N):
                declared_outputs.add(output_decl.name.name)
        
        # Collect all assigned variable names in the gauge body
        assigned_variables = set()
        self._collect_assigned_variables(gauge_node.stmts, assigned_variables)
        
        # Check for unassigned output variables
        unassigned_outputs = declared_outputs - assigned_variables
        
        if unassigned_outputs:
            unassigned_list = sorted(unassigned_outputs)
            if len(unassigned_list) == 1:
                error_msg = f"Gauge '{gauge_node.name.name}' declares output variable '{unassigned_list[0]}' but never assigns to it"
                hint_msg = f"Add an assignment like '{unassigned_list[0]} = expression;' in the gauge body"
            else:
                error_msg = f"Gauge '{gauge_node.name.name}' declares output variables {unassigned_list} but never assigns to them"
                hint_msg = f"Add assignments for all output variables in the gauge body"
            
            raise GeLBExTypeError(
                gauge_node,
                error_msg,
                hint_msg
            )
    
    def _collect_assigned_variables(self, stmts_list, assigned_variables):
        """
        Recursively collect all variable names that are assigned to in a list of statements.
        """
        for stmt in stmts_list.elements:
            if isinstance(stmt, VariableAssignmentStmt_N):
                # Simple variable assignment: x = expr;
                if isinstance(stmt.lhs, Identifier_N):
                    assigned_variables.add(stmt.lhs.name)
            elif isinstance(stmt, DestructuringAssignmentStmt_N):
                # Destructuring: {a, b, c} = Func(args);
                for target in stmt.targets:
                    if isinstance(target, Identifier_N):
                        assigned_variables.add(target.name)
            # Note: We could extend this to handle more complex assignment patterns like:
            # - Array element assignments: arr[i] = expr;
            # - Lattice selections: f.out[x|i] = expr; (but these aren't output variables)
            # For now, we focus on simple variable assignments which are typical for gauge outputs
