#!/usr/bin/env python3

class Node_N(object):
    """Base class (for all GeLB AST Node-types)"""
    def __str__(self):
        raise NotImplementedError()

    def eval(self):
        raise NotImplementedError()


class List_N(Node_N):
    def __init__(self):
        self.elements = []

    def append(self, element):
        self.elements.append(element)

    def __getitem__(self, i):
        return self.elements[i]

    def __len__(self):
        return len(self.elements)

    def __str__(self):
        result = (
            f"(List"
        )
        for element in self.elements:
            result += f" {str(element)}"
        result += ")"
        return result


class Program_N(Node_N):
    def __init__(self):
        self.simulation_name = None
        self.simulation_description = None
        self.global_constants = None
        self.list_of_lattice_constants_blocks = List_N()
        self.lattices = None
        self.list_of_initializers = List_N()
        self.list_of_dynamics = List_N()
        self.list_of_gauges = List_N()
        #self.list_of_functions = List_N()
        self.node_classes = None
        self.geometry = None

    def __str__(self):
        result = (
            f"(Program"
            f" {str(self.simulation_name)}"
            f" {str(self.simulation_description)}"
        )
        if self.global_constants is not None:
            result += f" {str(self.global_constants)}"
        if self.list_of_lattice_constants_blocks:  # if list is not empty...
            result += f" {str(self.list_of_lattice_constants_blocks)}"
        result += f" {str(self.lattices)}"
        result += f" {str(self.list_of_initializers)}"
        result += f" {str(self.list_of_dynamics)}"
        result += f" {str(self.list_of_gauges)}"
        result += f" {str(self.node_classes)}"
        result += f" {str(self.geometry)}"
        result += ")"
        return result


class Block_N(Node_N):
    def __init__(self, list_of_stmts):
        self.list_of_stmts = list_of_stmts


class GlobalConstantsBlock_N(Block_N):
    def __init__(self, list_of_stmts):
        super().__init__(list_of_stmts)

    def __str__(self):
        result = "(GlobalConstantsBlock"
        for stmt in self.list_of_stmts:
            result += f" {str(stmt)}"
        result += ")"
        return result


class LatticeConstantsBlock_N(Block_N):
    def __init__(self, lattice_name, list_of_stmts):
        self.lattice_name = lattice_name
        super().__init__(list_of_stmts)

    def __str__(self):
        result = f"(LatticeConstantsBlock {self.lattice_name}"
        for stmt in self.list_of_stmts:
            result += f" {str(stmt)}"
        result += ")"
        return result


class LatticesBlock_N(Node_N):
    def __init__(self, lattice_instances):
        self.lattice_instances = lattice_instances

    def __str__(self):
        result = "(LatticesBlock"
        for lattice_instance in self.lattice_instances:
            result += f" {str(lattice_instance)}"
        result += ")"
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
    def __init__(self, node_classes):
        self.node_classes = node_classes

    def __str__(self):
        result = f"(NodeClassesBlock"
        for node_class in self.node_classes:
            result += f" {node_class}"
        result += ")"
        return result


# TODO only allow inside NodeClassesBlock_N
class NodeClassInstaStmt_N(Node_N):
    def __init__(self, name, initializer, dynamic, gauge):
        self.name = name
        self.initializer = initializer
        self.dynamic = dynamic
        self.gauge = gauge

    def __str__(self):
        return (
            f"(NodeClassInstaStmt"
            f" {self.name}"
            f" {self.initializer}"
            f" {self.dynamic}"
            f" {self.gauge})"
        )


class InitializerBlock_N(Node_N):
    def __init__(self, name, stmts):
        self.name = name
        self.stmts = stmts

    def __str__(self):
        result = f"(Initializer {self.name}"
        for stmt in self.stmts:
            result += f" {stmt}"
        result += ")"
        return result


class DynamicBlock_N(Node_N):
    def __init__(self, name, stmts):
        self.name = name
        self.stmts = stmts

    def __str__(self):
        result = f"(Dynamic {self.name}"
        for stmt in self.stmts:
            result += f" {stmt}"
        result += ")"
        return result


class GaugeBlock_N(Node_N):
    def __init__(self, name, outputs, stmts):
        self.name = name
        self.outputs = outputs
        self.stmts = stmts

    def __str__(self):
        result = f"(Gauge {self.name}"
        for output in self.outputs:
            result += f" {output}"
        for stmt in self.stmts:
            result += f" {stmt}"
        result += ")"
        return result


class GeometryBlock_N(Node_N):
    def __init__(self, stmts):
        self.stmts = stmts

    def __str__(self):
        result = "(GeometryBlock"
        for stmt in self.stmts:
            result += f" {stmt}"
        result += ")"
        return result


class Identifier_N(Node_N):
    """Terminal AST-node"""
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"(Identifier {self.name})"


class Range_N(Node_N):
    def __init__(self, low, high):
        self.low = low
        self.high = high

    def __str__(self):
        lowRepres = self.low if self.low else "(RangePlaceholder Min)"
        highRepres = self.high if self.high else "(RangePlaceholder Max)"
        return f"(Range {lowRepres} {highRepres})"


class RectSelOfLatticeDFs_N(Node_N):
    """
    Rectangular selection of lattice DFs.
    """
    def __init__(self,
                 spatial_ranges,
                 dfs_range,
                 selection_type):
        self.spatial_ranges = spatial_ranges
        self.dfs_range = dfs_range
        self.selection_type = selection_type


class RectSelOfLatticeInDFs_N(RectSelOfLatticeDFs_N):
    def __init__(self,
                 spatial_ranges,
                 dfs_range):
        super().__init__(spatial_ranges, dfs_range, 'in')

    def __str__(self):
        result = "(RectSelOfLatticeInDFs"
        for spatial_range in self.spatial_ranges:
            result += f" {spatial_range}"
        result += f" {self.dfs_range}"
        result += ")"
        return result


class RectSelOfLatticeOutDFs_N(RectSelOfLatticeDFs_N):
    def __init__(self,
                 spatial_ranges,
                 dfs_range):
        super().__init__(spatial_ranges, dfs_range, 'out')

    def __str__(self):
        result = "(RectSelOfLatticeOutDFs"
        for spatial_range in self.spatial_ranges:
            result += f" {spatial_range}"
        result += f" {self.dfs_range}"
        result += ")"
        return result


# TODO implement, inspired by RectSelOfLatticeDFs_N
class RectSelOfArrayElems_N(Node_N):
    def __init__(self):
        raise NotImplementedError()


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
    def __init__(self, operator, left, right):
        self.operator = operator
        self.left = left
        self.right = right


class Mul_N(BinaryExpr_N):
    def __init__(self, left, right):
        super().__init__('*', left, right)

    def __str__(self):
        return f"(Mul {self.left} {self.right})"


class Div_N(BinaryExpr_N):
    def __init__(self, left, right):
        super().__init__('/', left, right)

    def __str__(self):
        return f"(Div {self.left} {self.right})"


class Add_N(BinaryExpr_N):
    def __init__(self, left, right):
        super().__init__('+', left, right)

    def __str__(self):
        return f"(Add {self.left} {self.right})"


class Sub_N(BinaryExpr_N):
    def __init__(self, left, right):
        super().__init__('-', left, right)

    def __str__(self):
        return f"(Sub {self.left} {self.right})"


class Pow_N(BinaryExpr_N):
    def __init__(self, left, right):
        super().__init__('^', left, right)

    def __str__(self):
        return f"(Pow {self.left} {self.right})"


class UnaryExpr_N(Node_N):
    def __init__(self, operator, value):
        self.operator = operator
        self.value = value


class NotExpr_N(UnaryExpr_N):
    def __init__(self, value):
        super().__init__('not', value)


class UnaryMinusExpr_N(UnaryExpr_N):
    def __init__(self, value):
        super().__init__('-', value)

    def __str__(self):
        return f"(UnaryMinusExpr {self.value})"


class IntLiteral_N(Node_N):
    """Terminal AST-node"""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return f"(IntLiteral {self.value})"


class RealLiteral_N(Node_N):
    """Terminal AST-node"""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return f"(RealLiteral {self.value})"


class BoolLiteral_N(Node_N):
    """Terminal AST-node"""
    def __init__(self, value):
        # Store as string, because we use lowercase, i.e.:
        # 'true' & 'false', instead of
        # 'True' & 'False' (which Python uses)
        self.value = str(value)

    def __str__(self):
        return f"(BoolLiteral {self.value})"


class StringLiteral_N(Node_N):
    """Terminal AST-node"""
    def __init__(self, value, field_name=None):
        self.value = value
        self.field_name = field_name

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
            result += f" {str(element)}"
        result += ")"
        return result


class Array1DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, dimensionality=1)


class Array2DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, dimensionality=2)


class Array3DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, dimensionality=3)


class Array4DLiteral_N(ArrayLiteralBase_N):
    def __init__(self, value):
        super().__init__(value, dimensionality=4)


# NOTE: later, we can distinguish (maybe) between:
#       - intrinsic &
#       - user-defined functions
class FunctionCall_N(Node_N):
    def __init__(self, args_list):
        self.args_list = args_list  # TODO: make this a =List_N= !


# TODO make Abstract Base Class
class Stmt_N(Node_N):
    def __str__(self):
        raise NotImplementedError()


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
    def __init__(self, data_type, name):
        self.data_type = data_type
        self.name = name

    def __str__(self):
        return (
            f"(VariableDeclarationStmt {self.name} {self.data_type})"
        )


class AssignmentStmt_N(Stmt_N):
    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs


class PaintNodesStmt_N(AssignmentStmt_N):
    def __init__(self, node_class, spatial_ranges):
        super().__init__(node_class, spatial_ranges)

    def __str__(self):
        result = f"(PaintNodesStmt {self.lhs}"
        for range in self.rhs:
            result += f" {range}"
        result += ")"
        return result


class VariableAssignmentStmt_N(AssignmentStmt_N):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return (
            f"(VariableAssignmentStmt {self.lhs} {self.rhs})"
        )


class LatticeAssignmentStmt_N(AssignmentStmt_N):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return (
            f"(LatticeAssignmentStmt {self.lhs} {self.rhs})"
        )


# TODO only allow inside UserFunctionBlock_N
class ReturnStmt_N(Node_N):
    pass


# TODO: implement this, based on GaugeBlock_N (only that here we also have inputs)
class FunctionBlock_N(Node_N):
    def __init__(self):
        raise NotImplementedError()
