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
    pass  # TODO: capture type (one of the few allowed options)
          # TODO: enforce options @__init__

class ArrayDataType_N(Node_N):
    pass  # TODO: capture element data-type & shape


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


# class FloatLiteral_N(Node_N):
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


class Array1DLiteral_N(Node_N):
    def __init__(self, value):
        # value is a Python list
        self.value = value

    def __str__(self):
        result = "(ArrayLiteral1D {"
        is_first_element = True
        for element in self.value:
            if is_first_element:
                is_first_element = False
                result = result + str(element)
            else:
                result = result + ", " + str(element)
        result = result + "})"
        return result


class Array2DLiteral_N(Node_N):
    def __init__(self, value):
        # value is a Python list of Array1DLiteral_N instances
        self.value = value

    def __str__(self):
        result = "(ArrayLiteral2D {"
        is_first_sub_array = True
        for sub_array in self.value:
            if is_first_sub_array:
                is_first_sub_array = False
                result = result + str(sub_array)
            else:
                result = result + ", " + str(sub_array)
        result = result + "})"
        return result


class Array3DLiteral_N(Node_N):
    def __init__(self, value):
        # value is a Python list of Array2DLiteral_N instances
        self.value = value

    def __str__(self):
        result = "(ArrayLiteral3D {"
        is_first_sub_array = True
        for sub_array in self.value:
            if is_first_sub_array:
                is_first_sub_array = False
                result = result + str(sub_array)
            else:
                result = result + ", " + str(sub_array)
        result = result + "})"
        return result


# class Array4DLiteral_N(Node_N):
#     TODO use np.array


# class List_N(Node_N):
#     def __init__(self):
#         self.value = None


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
    def __init__(self, name, value):
        self.name = name
        self.value = value


class VariableDeclarationStmt_N(Stmt_N):
    def __init__(self, name, value):
        self.name = name
        self.value = value


class AssignmentStmt_N(Stmt_N):
    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs


class VariableAssignmentStmt_N(AssignmentStmt_N):
    pass


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