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
        
        return node