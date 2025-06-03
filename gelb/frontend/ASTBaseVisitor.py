#!/usr/bin/env python3

from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import *


class ASTBaseVisitor:
    """
    Base class for all AST node-visitors.
    
    This class provides a dynamic dispatch mechanism for visiting AST nodes.
    Subclasses only need to implement visit methods for the specific node types 
    they care about, following the pattern visitNODE_CLASS_NAME(node, ast_root_node).
    
    The dynamic dispatch approach allows visitors to be selective about which 
    nodes they process, avoiding the need to implement empty methods for all 
    possible node types.
    """

    def visit(self, node, ast_root_node):
        """
        Visit a node.

        Calls ``visitNODE_CLASS_NAME`` on itself passing ``node``,
        where ``NODE_CLASS_NAME`` is the node's class.

        :param node: The node to visit.
        :param ast_root_node: The root node for the entire program.
               NOTE: To avoid having the AST as a global constant, we always
               pass the ast_root_node to the visitor-methods (some of which
               need to access information available near the top of the tree).
        :return: The return value of the called visitation method.
        """
        ast_node_type_name = type(node).__name__
        visitor_subclass_name = self.__class__.__name__
        visitation_method_name = f"visit{ast_node_type_name}"
        if hasattr(self, visitation_method_name):
            visitation_method = getattr(self, visitation_method_name, None)
            result = visitation_method(node, ast_root_node)
            return result
        else:
            raise GeLBExMissingASTVisitationMethod(
                visitor_subclass_name,
                visitation_method_name
            )
