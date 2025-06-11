#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError


class GaugeValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for validating gauge blocks.
    
    Validates that:
    1. All gauge blocks have output specifications
    2. Output specifications are not empty
    """
    
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # Visit all gauge blocks in the program
        if hasattr(node, 'gauges') and node.gauges:
            for gauge in node.gauges:
                self.visit(gauge, ast_root_node)
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
                "Gauges must specify outputs using 'out = {{type var1; type var2; ...}}'. "
                f"For example: 'gauge {node.name.name}(out = {{int result;}}) {{ ... }}'"
            )
        
        # Check if all output declarations are valid
        for output in node.outputs.elements:
            if not isinstance(output, VariableDeclarationStmt_N):
                raise GeLBExTypeError(
                    output,
                    f"Invalid output specification in gauge '{node.name.name}'",
                    "Gauge outputs must be variable declarations like 'int var;' or 'real result;'"
                )
        
        # Check that all declared output variables are assigned in the gauge body
        self._validate_output_assignments(node)
        
        return node
    
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
            # Note: We could extend this to handle more complex assignment patterns like:
            # - Array element assignments: arr[i] = expr;
            # - Lattice selections: f.out[x|i] = expr; (but these aren't output variables)
            # For now, we focus on simple variable assignments which are typical for gauge outputs