#!/usr/bin/env python3

from gelb.ASTBaseVisitor import ASTBaseVisitor
from gelb.ASTNodes import *
from gelb.utils.misc import GELB_KEYWORDS


class ASTValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for initial AST validation
    """

    def visitProgram_N(self, node: Program_N):
        # (1) check that all required children are present, a valid number of
        #     times
        # TODO

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_ast_fields():
            self.visit(getattr(node, field))

    def visitList_N(
            self,
            node: List_N
    ):
        # descend into child nodes, to check that they are valid
        # List_N is the only component of the GeLB AST which has a field that
        # is NOT derived from Node_N (specifically, List_N.elements is a
        # plain Python list). So, we need to use some custom logic here.
        for field in node.elements:
            self.visit(field)

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N
    ):
        # (1) check that all required elements are present
        # TODO ensure they are not None, by iterating over node.get_ast_fields()

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_ast_fields():
            self.visit(getattr(node, field))

    def visitIdentifier_N(self, node: Identifier_N):
        # Nothing to do here, because ANTLR4 already catches problems with
        # identifiers (including the case when the user tries to use a GeLB
        # keyword as an identifier).
        # TODO: improve the error-message for the keyword-used-as-identifier
        #       error, by capturing the =msg= text produced by ANTLR4.
        pass

    # def visitScalarDataType_N(node:ScalarDataType_N):
    #     supported_scalar_types = [
    #         'bool',  # boolean
    #         'int64', 'int32', 'int16', 'int8', 'int',  # integer
    #         'real64', 'real32', 'real16', 'real'  # real
    #     ]
    #     if node.data_type not in supported_scalar_types:
    #         raise TypeError(
    #             f"<<<GeLB-Error>>> {str(node.data_type)} is not a valid"
    #             f" scalar data-type!"
    #             f"\nHint: you can use one of the following values: "
    #             f"{supported_scalar_types}"
    #         )


    # def visitIntLiteral_N(node:IntLiteral_N):
    #     return isinstance(node.value, int)
    #
    # def visitRealLiteral_N(node:RealLiteral_N):
    #     return isinstance(node.value, float)
    #
    # def visitBoolLiteral_N(node:BoolLiteral_N):
    #     return isinstance(node.value, bool)
    #
    # def visitStringLiteral_N(node:StringLiteral_N):
    #     return (
    #             isinstance(node.value, str) and
    #             isinstance(node.field_name, str) and (
    #                     (node.field_name == "simulation_name") or
    #                     (node.field_name == "simulation_description")
    #             )
    #     )

    def visitLatticeOutSelectionAssignmentStmt_N(
            self,
            node: LatticeOutSelectionAssignmentStmt_N
    ):
        # (1) check that all required elements are present
        # TODO ensure they are not None, by iterating over node.get_ast_fields()

        # (2) descend into child nodes, to check that they are valid
        for field in node.get_ast_fields():
            print(f"<<<DEBUG>>> {field}, {type(getattr(node, field))}")
            self.visit(getattr(node, field))

