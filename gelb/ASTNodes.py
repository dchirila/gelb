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

# class Id_N(Node_N):
#     def __init__(self):
#         pass

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

# class BinaryExpr_N(Node_N):
#     def __init__(self):
#         pass

# class UnaryExpr_N(Node_N):
#     def __init__(self):
#         pass

# class IntLiteral_N(Node_N):
#     def __init__(self):
#         self.value = None

# class FloatLiteral_N(Node_N):
#     def __init__(self):
#         self.value = None

# class BoolLiteral_N(Node_N):
#     def __init__(self):
#         self.value = None

class StringLiteral_N(Node_N):
    def __init__(self, value):
        self.value = value
#
# class List_N(Node_N):
#     def __init__(self):
#         self.value = None

# class TODO_N(Node_N):
#     def __init__(self):
#         pass