#!/usr/bin/env python3

from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError


# Block types where f.out[...] is allowed
_FOUT_ALLOWED = {'initializer', 'dynamic'}
# Block types where f.in[...] is allowed
_FIN_ALLOWED = {'dynamic', 'gauge'}


class LatticeAccessContextValidator:
    """
    Validates that lattice selections appear only in appropriate block contexts.

    Rules:
      - f.out[...] (RectSelOfLatticeOutDFs_N) only in initializer and dynamic
      - f.in[...]  (RectSelOfLatticeInDFs_N)  only in dynamic and gauge
      - No lattice selections in global_constants
    """

    def validate(self, ast):
        """Validate all lattice access contexts in the program AST."""
        if not isinstance(ast, Program_N):
            return

        if ast.global_constants is not None:
            self._check_block(ast.global_constants, 'global_constants')

        if ast.initializers is not None:
            for init in ast.initializers.elements:
                self._check_block(init, 'initializer')

        if ast.dynamics is not None:
            for dyn in ast.dynamics.elements:
                self._check_block(dyn, 'dynamic')

        if ast.gauges is not None:
            for gauge in ast.gauges.elements:
                self._check_block(gauge, 'gauge')

        if ast.functions is not None:
            for func in ast.functions.elements:
                self._check_block(func, 'function')

    def _check_block(self, block, block_type):
        """Recursively search a block for lattice selections and validate."""
        self._walk(block, block_type)

    def _walk(self, node, block_type):
        """Recursively walk AST nodes looking for lattice selections."""
        if node is None:
            return

        if isinstance(node, RectSelOfLatticeOutDFs_N):
            if block_type not in _FOUT_ALLOWED:
                if block_type == 'function':
                    raise GeLBExTypeError(
                        node,
                        "GeLB functions cannot have side effects",
                        "Functions cannot write to lattices (f.out[...]). "
                        "Pass data through function parameters instead."
                    )
                block_label = block_type.replace('_', ' ')
                raise GeLBExTypeError(
                    node,
                    f"'f.out[...]' cannot appear in {block_label} block",
                    "f.out[...] can only be used in initializer and dynamic "
                    "blocks (it writes to the lattice)"
                )

        if isinstance(node, RectSelOfLatticeInDFs_N):
            if block_type not in _FIN_ALLOWED:
                if block_type == 'function':
                    raise GeLBExTypeError(
                        node,
                        "GeLB functions cannot have side effects",
                        "Functions cannot read from lattices (f.in[...]). "
                        "Pass lattice data through function parameters instead."
                    )
                block_label = block_type.replace('_', ' ')
                raise GeLBExTypeError(
                    node,
                    f"'f.in[...]' cannot appear in {block_label} block",
                    "f.in[...] can only be used in dynamic and gauge "
                    "blocks (it reads from the lattice)"
                )

        # Recurse into child nodes
        for attr_name in vars(node):
            if attr_name.startswith('_'):
                continue
            child = getattr(node, attr_name, None)
            if child is None:
                continue
            if isinstance(child, Node_N):
                self._walk(child, block_type)
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, Node_N):
                        self._walk(item, block_type)
            elif hasattr(child, 'elements') and isinstance(
                    getattr(child, 'elements', None), list):
                for item in child.elements:
                    if isinstance(item, Node_N):
                        self._walk(item, block_type)
