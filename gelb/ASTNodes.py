#!/usr/bin/env python3

class Node_N(object):
    """Base class (for all GeLB AST Node-types)"""
    def eval(self):
        raise NotImplementedError()


class Program_N(Node_N):
    def __init__(self):
        self.simulation_name = None
        self.simulation_description = None
        self.list_of_lattices = None
        # self.global_constants = None
        # self.list_of_initializers = None
        # self.list_of_dynamics = None
        # self.list_of_gauges = None
        # self.list_of_functions = None
        # self.list_of_node_classes = None
        # self.geometry = None


class Block_N(Node_N):
    def __init__(self, list_of_stmts):
        self.list_of_stmts = list_of_stmts

    def __str__(self):
        raise NotImplementedError()


class GlobalConstantsBlock_N(Block_N):
    def __init__(self, list_of_stmts):
        super().__init__(list_of_stmts)

    def __str__(self):
        result = "(GlobalConstantsBlock"
        for stmt in self.list_of_stmts:
            result = result + f" {str(stmt)}"
        result = result + ")"
        return result


class LatticeConstantsBlock_N(Block_N):
    def __init__(self, lattice_name, list_of_stmts):
        self.lattice_name = lattice_name
        super().__init__(list_of_stmts)

    def __str__(self):
        result = f"(LatticeConstantsBlock {self.lattice_name}"
        for stmt in self.list_of_stmts:
            result = result + f" {str(stmt)}"
        result = result + ")"
        return result


class LatticesBlock_N(Node_N):
    def __init__(self, lattice_instances):
        self.lattice_instances = lattice_instances

    def __str__(self):
        result = "(LatticesBlock"
        for lattice_instance in self.lattice_instances:
            result = result + f" {str(lattice_instance)}"
        result = result + ")"
        return result


# TODO only allow inside LatticesBlock_N
class LatticeInstaStmt_N(Node_N):
    def __init__(self, name, d, q, df_type, size):
        self.name = name
        self.d = d
        self.q = q
        self.df_type = df_type
        self.size = size

    def __str__(self):
        return (
            f"(LatticeInstaStmt {self.name} {self.d} {self.q} "
            f"{self.df_type} {self.size})"
        )


class NodeClassesBlock_N(Node_N):
    pass


# TODO only allow inside NodeClassesBlock_N
class NodeClassInstaStmt_N(Node_N):
    pass


class UserFunctionBlock_N(Node_N):
    pass


# TODO only allow inside UserFunctionBlock_N
class ReturnStmt_N(Node_N):
    pass


# class LatticeConstantsBlock_N(Node_N):
#     def __init__(self):
#         pass


# class LatticeBlock_N(Node_N):
#     def __init__(self):
#         pass


# class NodeClassesBlock_N(Node_N):
#     def __init__(self):
#         pass


# class InitializerBlock_N(Node_N):
#     def __init__(self):
#         pass


# class DynamicBlock_N(Node_N):
#     def __init__(self):
#         pass


# class GaugeBlock_N(Node_N):
#     def __init__(self):
#         pass


# class FunctionBlock_N(Node_N):
#     def __init__(self):
#         pass


# class GeometryBlock_N(Node_N):
#     def __init__(self):
#         pass


# class Expr_N(Node_N):
#     def __init__(self):
#         pass


class Identifier_N(Node_N):
    def __init__(self, name):
        self.name = name


# class RectSelOfLatticeDFs_N(Node_N):
#     """
#     Rectangular selection of lattice DFs.
#
#     TODO: store type of lattice selection (IN or OUT)
#     """
#     def __init__(self):
#         pass


# class RectSelOfArrayElems_N(Node_N):
#     def __init__(self):
#         pass

class ScalarDataType_N(Node_N):
    supported_scalar_types = [
        'bool',  # boolean
        'int64', 'int32', 'int16', 'int8', 'int',  # integer
        'real64', 'real32', 'real16', 'real'  # real
    ]
    def __init__(self, value):
        if value not in self.supported_scalar_types:
            raise TypeError(
                f"<<<GeLB-Error>>> {str(value)} is not a valid scalar data-type!"
                f"\nHint: you can use one of the following values: "
                f"{self.supported_scalar_types}"
            )
        self.value = value

    def __str__(self):
        return f"(ScalarDataType {self.value})"


class ArrayDataType_N(Node_N):
    def __init__(self, element_data_type, shape):
        self.element_data_type = element_data_type
        self.shape = shape  # might be either Array1DLiteral_N or IntLiteral_N

    def __str__(self):
        return (
            f"(ArrayDataType {self.element_data_type} {self.shape})"
        )


class BinaryExpr_N(Node_N):
    def __init__(self, left, right):
        self.left = left
        self.righ = right


class Add_N(BinaryExpr_N):
    def __init__(self, left, right):
        super().__init__(left, right)


# class UnaryExpr_N(Node_N):
#     def __init__(self):
#         pass


class IntLiteral_N(Node_N):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return f"(IntLiteral {self.value})"


# class RealLiteral_N(Node_N):
#     def __init__(self, value):
#         self.value = value


# class BoolLiteral_N(Node_N):
#     def __init__(self, value):
#         self.value = value


class StringLiteral_N(Node_N):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return f"(StringLiteral {self.value})"


# base-class for Array{1,2,3,4}DLiteral_N
class ArrayLiteralBase_N(Node_N):
    def __init__(self, value, dimensionality):
        # value is a Python list, where the elements can be (depending on the
        # dimensionality of the derived class):
        # - IntLiteral_N @Array1DLiteral_N
        #   TODO: replace with ScalarExpr_N or Expr_N later (general exprs).
        # - Array1DLiteral_N @Array2DLiteral_N
        # - Array2DLiteral_N @Array3DLiteral_N
        # - Array3DLiteral_N @Array4DLiteral_N
        self.value = value
        self.dimensionality = dimensionality

    def __str__(self):
        result = f"(ArrayLiteral{str(self.dimensionality)}D"
        for element in self.value:
            result = result + f" {str(element)}"
        result = result + ")"
        return result


class Array1DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, 1)


class Array2DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, 2)


class Array3DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, 3)


class Array4DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, 4)


# NOTE: later, we can distinguish (maybe) between:
#       - intrinsic &
#       - user-defined functions
class FunctionCall_N(Node_N):
    def __init__(self, args_list):
        self.args_list = args_list  # TODO: make this a =List_N= !


# TODO make Abstract Base Class
class Stmt_N(Node_N):
    pass


# NOTE: declaration AND assignment!
class ConstantDefinitionStmt_N(Stmt_N):
    def __init__(self, data_type, name, value):
        self.data_type = data_type
        self.name = name
        self.value = value

    def __str__(self):
        return (
            f"(ConstantDefinitionStmt {self.name} {self.data_type} {self.value})"
        )


class VariableDeclarationStmt_N(Stmt_N):
    def __init__(self, name, value):
        self.name = name
        self.value = value


class AssignmentStmt_N(Stmt_N):
    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs


class VariableAssignmentStmt_N(AssignmentStmt_N):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return (
            f"(VariableAssignmentStmt {self.lhs} {self.rhs})"
        )


class LatticeAssignmentStmt_N(AssignmentStmt_N):
    pass


# TODO only allow inside GeometryBlock_N
class GeometryAssignmentStmt_N(AssignmentStmt_N):
    pass


# class TODO_N(Node_N):
#     def __init__(self):
#         pass