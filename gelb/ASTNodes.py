#!/usr/bin/env python3

class Node_N(object):
    """Base class (for all GeLB AST Node-types)"""
    def eval(self):
        raise NotImplementedError()

class Program_N(Node_N):
    def __init__(self):
        self.configuration = None
        self.listof_lattice_properties = None
        self.listof_lattice_instances = None
        self.listof_node_classes = None
        self.listof_initializers = None
        self.listof_dynamics = None
        self.listof_gauges = None
        self.listof_functions = None
        self.geometry = None

class GlobalConfig_N(Node_N):
    def __init__(self):
        pass

class SimulationMetadata_N(Node_N):
    def __init__(self):
        pass

class LatticeProperties_N(Node_N):
    def __init__(self):
        pass

class Lattices_N(Node_N):
    def __init__(self):
        pass

class NodeClasses_N(Node_N):
    def __init__(self):
        pass

class Initializer_N(Node_N):
    def __init__(self):
        pass

class Dynamic_N(Node_N):
    def __init__(self):
        pass

class Gauge_N(Node_N):
    def __init__(self):
        pass

class Function_N(Node_N):
    def __init__(self):
        pass

class Geometry_N(Node_N):
    def __init__(self):
        pass

class Expr_N(Node_N):
    def __init__(self):
        pass

class Id_N(Node_N):
    def __init__(self):
        pass

class RectSelOfLatticeDFs_N(Node_N):
    """
    Rectangular selection of lattice DFs.

    TODO: store type of lattice selection (IN or OUT)
    """
    def __init__(self):
        pass

class RectSelOfArrayElems_N(Node_N):
    def __init__(self):
        pass

class BinaryExpr_N(Node_N):
    def __init__(self):
        pass

class UnaryExpr_N(Node_N):
    def __init__(self):
        pass

class IntLiteral_N(Node_N):
    def __init__(self):
        self.value = None

class FloatLiteral_N(Node_N):
    def __init__(self):
        self.value = None

class BoolLiteral_N(Node_N):
    def __init__(self):
        self.value = None

class StringLiteral_N(Node_N):
    def __init__(self):
        self.value = None

class List_N(Node_N):
    def __init__(self):
        self.value = None

class TODO_N(Node_N):
    def __init__(self):
        pass