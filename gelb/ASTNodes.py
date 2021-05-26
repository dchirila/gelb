#!/usr/bin/env python3

class Node_N(object):
    """Base class (for all GeLB AST Node-types)"""
    def eval(self):
        raise NotImplementedError()


class Program_N(Node_N):
    def __init__(self):
        self.simulation_name = None
        self.simulation_description = None
        # self.list_of_lattices = None
        # self.global_constants = None
        # self.list_of_initializers = None
        # self.list_of_dynamics = None
        # self.list_of_gauges = None
        # self.list_of_functions = None
        # self.list_of_node_classes = None
        # self.geometry = None


class SetSimulationNameStmt_N(Node_N):
    pass


class SetSimulationDescriptionStmt_N(Node_N):
    pass


# class LatticeProperties_N(Node_N):
#     def __init__(self):
#         pass


# class Lattices_N(Node_N):
#     def __init__(self):
#         pass


# class NodeClasses_N(Node_N):
#     def __init__(self):
#         pass


# class Initializer_N(Node_N):
#     def __init__(self):
#         pass


# class Dynamic_N(Node_N):
#     def __init__(self):
#         pass


# class Gauge_N(Node_N):
#     def __init__(self):
#         pass


# class Function_N(Node_N):
#     def __init__(self):
#         pass


# class Geometry_N(Node_N):
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
                "<<<GeLB-Error>>> " + str(value) +
                " is not a valid scalar data-type!" +
                "\nHint: you can use one of the following values: " +
                str(self.supported_scalar_types)
            )
        self.value = value

    def __str__(self):
        return "(ScalarDataType " + self.value + ")"


class ArrayDataType_N(Node_N):
    def __init__(self, element_data_type, shape):
        self.element_data_type = element_data_type
        self.shape = shape  # might be either Array1DLiteral_N or IntLiteral_N

    def __str__(self):
        return (
            "(ArrayDataType " +
            str(self.element_data_type) +
            " " +
            str(self.shape) +
            ")"
        )


class BinaryExpr_N(Node_N):
    def __init__(self, left, right):
        self.left = left
        self.righ = right


class Add_N(BinaryExpr_N):
    def __init__(self, left, right):
        super(Add_N, self).__init__(left, right)


# class UnaryExpr_N(Node_N):
#     def __init__(self):
#         pass


class IntLiteral_N(Node_N):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "(IntLiteral " + str(self.value) + ")"


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
        return "(StringLiteral " + self.value + ")"


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
        result = "(ArrayLiteral" + str(self.dimensionality) + "D {"
        is_first_element = True
        for element in self.value:
            if is_first_element:
                is_first_element = False
                result = result + str(element)
            else:
                result = result + ", " + str(element)
        result = result + "})"
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
            "(ConstantDefinitionStmt " +
            str(self.name) + " " +
            str(self.data_type) + " " +
            str(self.value) +
            ")"
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
            "(VariableAssignmentStmt " +
            str(self.lhs) +
            " " +
            str(self.rhs) +
            ")"
        )


class LatticeAssignmentStmt_N(AssignmentStmt_N):
    pass


# TODO only allow inside GeometryBlock_N
class GeometryAssignmentStmt_N(AssignmentStmt_N):
    pass


class LatticesBlock_N(Node_N):
    pass


# TODO only allow inside LatticesBlock_N
class LatticeInstantiationStmt_N(Node_N):
    pass


class NodeClassesBlock_N(Node_N):
    pass


# TODO only allow inside NodeClassesBlock_N
class NodeClassInstantiationStmt_N(Node_N):
    pass


class UserFunctionBlock_N(Node_N):
    pass


# TODO only allow inside UserFunctionBlock_N
class ReturnStmt_N(Node_N):
    pass


# class TODO_N(Node_N):
#     def __init__(self):
#         pass