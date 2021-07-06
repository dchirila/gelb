#!/usr/bin/env python3

from abc import ABC, abstractmethod
from gelb.SymbolsTable import SymbolsTable
from gelb.SymbolReference import SymbolReference
from gelb.ASTBaseVisitor import ASTBaseVisitor


class Node_N(ABC):
    """
    Base class (for all GeLB AST Node-types)
    """
    def __init__(self, code_range):
        self.code_range = code_range

    @abstractmethod
    def __str__(self):
        pass

    def get_children(self):
        # special treatment for List_N
        if isinstance(self, List_N):
            return self.elements
        else:
            children = [
                getattr(self, field) for field in dir(self) if not (
                        field.startswith('_') or
                        field.startswith('code_range') or
                        field.startswith('get_children') or
                        field.startswith('iterate_over_ast_fields') or
                        field.startswith('get_referenced_symbols') or
                        field.startswith('is_terminal_node') or
                        field.startswith('append') or  # from List_N
                        # exclude the symbol-table
                        field.startswith('symbol_defs')
                )
            ]
            return children

    def get_referenced_symbols(self):
        result = set()
        # recursive descend
        for child in self.get_children():
            if child is not None:
                result |= child.get_referenced_symbols()
        return result

    def is_terminal_node(self):
        return False  # False unless otherwise

    # def accept(self, visitor):
    #     raise NotImplementedError()

    # @abstractmethod
    # def eval(self):
    #     pass


class List_N(Node_N):
    """
    Wrapper for Python lists, with some GeLB-related functionality.

    Used in various places throughout the GeLB AST.
    """
    def __init__(self, code_range):
        super().__init__(code_range)  # pass code_range to superclass
        self.elements = []

    def append(self, element):
        self.elements.append(element)

    def __getitem__(self, i):
        return self.elements[i]

    def __len__(self):
        return len(self.elements)

    def __setitem__(self, key, value):
        self.elements[key] = value

    def __str__(self):
        return f"(List {' '.join(f'{e}' for e in self.elements)})"


class Program_N(Node_N):
    """
    Represents the root AST node for a GeLB program.
    """
    def __init__(self, code_range):
        super().__init__(code_range)
        self.simulation_name = None
        self.simulation_description = None
        self.global_constants = None
        self.lattices = None
        self.initializers = None
        self.dynamics = None
        self.gauges = None
        # self.functions = None
        self.node_classes = None
        self.geometry = None
        # symbol_defs table (built after AST construction)
        self.symbol_defs = None

    def __str__(self):
        result = (
            f"(Program"
            f" {str(self.simulation_name)}"
            f" {str(self.simulation_description)}"
        )
        if self.global_constants is not None:
            result += f" {str(self.global_constants)}"
        result += f" {str(self.lattices)}"
        result += f" {str(self.initializers)}"
        result += f" {str(self.dynamics)}"
        result += f" {str(self.gauges)}"
        result += f" {str(self.node_classes)}"
        result += f" {str(self.geometry)}"
        result += ")"
        return result


class Stmt_N(Node_N):
    """Base-class for all types of GeLB statements."""
    @abstractmethod
    def __str__(self):
        pass


class Expr_N(Node_N):
    """Base-class for all types of GeLB expression-elements."""
    @abstractmethod
    def __str__(self):
        pass


class SetSimulationNameStmt_N(Stmt_N):
    """
    Represents an instruction to set the simulation name.

    Example of corresponding code:

    simulation_name("test");
    """
    def __init__(self, code_range, name):
        super().__init__(code_range)
        self.name = name

    def __str__(self):
        return f"(SetSimulationNameStmt {self.name})"


class SetSimulationDescriptionStmt_N(Stmt_N):
    """
    Represents an instruction to set the simulation's description.

    Example of corresponding code:

    simulation_description(
    "This is
    a test"
    );

    NOTE: The description may be a multi-line string.
    """
    def __init__(self, code_range, description):
        super().__init__(code_range)
        self.description = description

    def __str__(self):
        return f"(SetSimulationDescriptionStmt {self.description})"


class Block_N(Node_N):
    """
    Base-class for larger AST sub-trees.

    All derived classes have a list of statements, enclosed within curly
    braces (with a preamble which depends on the specific type of block).
    """
    def __init__(self, code_range, stmts):
        super().__init__(code_range)
        self.stmts = stmts
        self.symbol_defs = None

    @abstractmethod
    def __str__(self):
        pass


class GlobalConstantsBlock_N(Block_N):
    """
    Represents the block of global constants.

    The constants defined within this block are visible in all other blocks.
    """
    def __str__(self):
        return (
            f"(GlobalConstantsBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class LatticesBlock_N(Block_N):
    """
    Represents the block (one per program) of lattice-instantiations.
    """
    def __str__(self):
        return (
            f"(LatticesBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class LatticeInstaStmt_N(Node_N):
    """
    Represents a lattice-instantiation statement.

    TODO (validation): only allow inside LatticesBlock_N
    """
    def __init__(self, code_range, name, d, q, df_type, size):
        super().__init__(code_range)
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


class NodeClassesBlock_N(Block_N):
    """
    Represents the block (one per program) of node-classes.
    """
    def __str__(self):
        return (
            f"(NodeClassesBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class NodeClassInstaStmt_N(Node_N):
    """
    Represents a node-class-instantiation statement.

    TODO (validation): only allow inside NodeClassesBlock_N
    TODO (GeLB-v1): allow multiple {initializers, dynamics, gauges}
    """
    def __init__(self, code_range, name, initializer, dynamic, gauge):
        super().__init__(code_range)
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


class InitializerBlock_N(Block_N):
    """
    Represents an initializer-block (one or more per program).
    """
    def __init__(self, code_range, name, stmts):
        super().__init__(code_range, stmts)
        self.name = name

    def __str__(self):
        return (
            f"(Initializer"
            f" {self.name}"
            f" {' '.join(f'{e}' for e in self.stmts)})"
        )


class DynamicBlock_N(Block_N):
    """
    Represents a dynamic-block (one or more per program).
    """
    def __init__(self, code_range, name, stmts):
        super().__init__(code_range, stmts)
        self.name = name

    def __str__(self):
        return (
            f"(Dynamic"
            f" {self.name}"
            f" {' '.join(f'{e}' for e in self.stmts)})"
        )


class GaugeBlock_N(Block_N):
    """
    Represents a gauge-block (one or more per program).
    """
    def __init__(self, code_range, name, outputs, stmts):
        super().__init__(code_range, stmts)
        self.name = name
        self.outputs = outputs

    def __str__(self):
        return (
            f"(Gauge"
            f" {self.name}"
            f" {' '.join(f'{e}' for e in self.outputs)}"
            f" {' '.join(f'{e}' for e in self.stmts)})"
        )


class GeometryBlock_N(Block_N):
    """
    Represents the block (one per program) of node-painting statements.
    """
    def __str__(self):
        return (
            f"(GeometryBlock {' '.join(f'{e}' for e in self.stmts)})"
        )


class Identifier_N(Expr_N):
    """
    Represents an identifier.
    """
    def __init__(self, code_range, name):
        super().__init__(code_range)
        self.name = name

    def __str__(self):
        return f"(Identifier {self.name})"

    def get_referenced_symbols(self):
        result = set()
        result.add(
            SymbolReference(self.name, self.code_range)
        )
        return result

    def is_terminal_node(self):
        return True


class Range_N(Node_N):
    """
    Represents an index-range.
    """
    def __init__(self, code_range, low, high):
        super().__init__(code_range)
        self.low = low
        self.high = high

    def __str__(self):
        low_repres = self.low if self.low else "(RangePlaceholder Min)"
        high_repres = self.high if self.high else "(RangePlaceholder Max)"
        return f"(Range {low_repres} {high_repres})"


class RectSel_N(Expr_N):
    """
    Base-class for rectangular selections of elements.
    """
    def __init__(self, code_range, element_ranges):
        super().__init__(code_range)
        self.element_ranges = element_ranges

    def __getitem__(self, i):
        return self.element_ranges[i]

    def __len__(self):
        return len(self.element_ranges)

    @abstractmethod
    def __str__(self):
        pass


class RectSelOfLatticeDFs_N(RectSel_N):
    """
    Base-class for rectangular selection of lattice IN/OUT DFs.

    NOTE: Last element in self.element_ranges represents the DFs-range.
    """
    def __init__(self, code_range, lattice_name, element_ranges):
        super().__init__(code_range, element_ranges)
        self.lattice_name = lattice_name

    @abstractmethod
    def __str__(self):
        pass


class RectSelOfLatticeInDFs_N(RectSelOfLatticeDFs_N):
    """
    Rectangular selection of lattice IN DFs.

    NOTE: Last element in self.element_ranges represents the DFs-range.
    """
    def __str__(self):
        return (
            f"(RectSelOfLatticeInDFs"
            f" {self.lattice_name}"
            f" {' '.join(f'{e}' for e in self.element_ranges)})"
        )


class RectSelOfLatticeOutDFs_N(RectSelOfLatticeDFs_N):
    """
    Rectangular selection of lattice OUT DFs.

    NOTE: Last element in self.element_ranges represents the DFs-range.
    """
    def __str__(self):
        return (
            f"(RectSelOfLatticeOutDFs"
            f" {self.lattice_name}"
            f" {' '.join(f'{e}' for e in self.element_ranges)})"
        )


class RectSelOfArrayElems_N(RectSel_N):
    """
    Rectangular selection of array elements.
    """
    def __init__(self, code_range, array_name, element_ranges):
        super().__init__(code_range, element_ranges)
        self.array_name = array_name

    def __str__(self):
        return (
            f"(RectSelOfArrayElems"
            f" {self.array_name}"
            f" {' '.join(f'{e}' for e in self.element_ranges)})"
        )


class DataType_N(Node_N):
    """
    Base-class for all GeLB data-types.
    """
    def __init__(self, code_range, scalar_dtype):
        super().__init__(code_range)
        self.scalar_dtype = scalar_dtype

    @abstractmethod
    def __str__(self):
        pass


class ScalarDataType_N(DataType_N):
    """
    Represents a scalar data-type (for variables & constants).
    """
    def __str__(self):
        return f"(ScalarDataType {self.scalar_dtype})"

    def is_terminal_node(self):
        return True

    def get_children(self):
        return set()


class ArrayDataType_N(DataType_N):
    """
    Represents an array data-type (for variables & constants).
    """
    def __init__(self, code_range, scalar_dtype, shape):
        super().__init__(code_range, scalar_dtype)
        self.shape = shape  # might be either Array1DLiteral_N or IntLiteral_N

    def __str__(self):
        return (
            f"(ArrayDataType {self.scalar_dtype} {self.shape})"
        )


class BinaryExpr_N(Expr_N):
    """
    Base-class for all GeLB binary expressions.
    """
    def __init__(self, code_range, left, right):
        super().__init__(code_range)
        self.left = left
        self.right = right

    @abstractmethod
    def __str__(self):
        pass


class Mul_N(BinaryExpr_N):
    """
    Represents a multiplication (*) binary expression.
    """
    def __str__(self):
        return f"(Mul {self.left} {self.right})"


class Div_N(BinaryExpr_N):
    """
    Represents a division (/) binary expression.
    """
    def __str__(self):
        return f"(Div {self.left} {self.right})"


class Add_N(BinaryExpr_N):
    """
    Represents an addition (+) binary expression.
    """
    def __str__(self):
        return f"(Add {self.left} {self.right})"


class Sub_N(BinaryExpr_N):
    """
    Represents a subtraction (-) binary expression.
    """
    def __str__(self):
        return f"(Sub {self.left} {self.right})"


class Pow_N(BinaryExpr_N):
    """
    Represents a raise-to-power (^) binary expression.
    """
    def __str__(self):
        return f"(Pow {self.left} {self.right})"


class UnaryExpr_N(Expr_N):
    """
    Base-class for all GeLB unary expressions.
    """
    def __init__(self, code_range, value):
        super().__init__(code_range)
        self.value = value

    @abstractmethod
    def __str__(self):
        pass


class NotExpr_N(UnaryExpr_N):
    """
    Represents a logical negation (not) unary expression.
    """
    def __str__(self):
        return f"(NotExpr {self.value})"


class UnaryMinusExpr_N(UnaryExpr_N):
    """
    Represents an arithmetic negation (-) unary expression.

    NOTE: This is how negative numbers are represented in GeLB (since the
    lexer only knows about positive numbers).
    """
    def __str__(self):
        return f"(UnaryMinusExpr {self.value})"


class Literal_N(Expr_N):
    """
    Base-class for all GeLB literals.
    """
    def __init__(self, code_range, value):
        super().__init__(code_range)
        self.value = value

    @abstractmethod
    def __str__(self):
        pass

    def is_terminal_node(self):
        return True


class IntLiteral_N(Literal_N):
    """
    Represents an integer literal.
    """
    def __str__(self):
        return f"(IntLiteral {self.value})"

    def get_referenced_symbols(self):
        return set()


class RealLiteral_N(Literal_N):
    """
    Represents a real literal.
    """
    def __str__(self):
        return f"(RealLiteral {self.value})"

    def get_referenced_symbols(self):
        return set()


class BoolLiteral_N(Literal_N):
    """
    Represents a boolean literal.

    NOTE: In GeLB, we use lowercase ('true' & 'false'), unlike Python,
    which capitalizes the first letter ('True' & 'False').
    """
    def __str__(self):
        return f"(BoolLiteral {self.value})"

    def get_referenced_symbols(self):
        return set()


class StringLiteral_N(Literal_N):
    """
    Represents a string literal.

    NOTE: In GeLB-v1, this class is only used for setting the name and the
    description of the simulations.
    """
    def __str__(self):
        return f"(StringLiteral {self.value})"

    def get_children(self):
        return set()


class ArrayLiteral_N(Literal_N):
    """
    Base-class for Array{1,2,3,4}DLiteral_N.

    NOTE: value has a different type for each sub-class.
    """
    @abstractmethod
    def __str__(self):
        pass


class Array1DLiteral_N(ArrayLiteral_N):
    """
    Represents a 1D array literal.

    NOTE: value is a List_N with elements of type Expr_N
    """
    def __str__(self):
        return (
            f"(ArrayLiteral1D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


class Array2DLiteral_N(ArrayLiteral_N):
    """
    Represents a 2D array literal.

    NOTE: value is a List_N with elements of type Array1DLiteral_N.
    """
    def __str__(self):
        return (
            f"(ArrayLiteral2D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


class Array3DLiteral_N(ArrayLiteral_N):
    """
    Represents a 3D array literal.

    NOTE: value is a List_N with elements of type Array2DLiteral_N.
    """
    def __str__(self):
        return (
            f"(ArrayLiteral3D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


class Array4DLiteral_N(ArrayLiteral_N):
    """
    Represents a 4D array literal.

    NOTE: value is a List_N with elements of type Array3DLiteral_N.
    """
    def __str__(self):
        return (
            f"(ArrayLiteral4D"
            f" {' '.join(f'{str(e)}' for e in self.value)})"
        )


# class FunctionCall_N(Node_N):
#     """
#     Represents a call of an intrinsic / user-defined function.
#     """
#     def __init__(self, code_range, args_list):
#         super().__init__(code_range)
#         self.args_list = args_list  # TODO: make this a =List_N= !


class ConstantDefinitionStmt_N(Stmt_N):
    """
    Represents a constant-definition statement.

    NOTE: declaration AND immediate assignment!
    """
    def __init__(self, code_range, data_type, name, value):
        super().__init__(code_range)
        self.data_type = data_type
        self.name = name
        self.value = value

    def __str__(self):
        return (
            f"(ConstantDefinitionStmt"
            f" {self.name} {self.data_type} {self.value}"
            f")"
        )


class VariableDeclarationStmt_N(Stmt_N):
    """
    Represents a variable-declaration statement.

    NOTE: No immediate assignment -- in GeLB-v0, we separate the variable
    declaration from the assignment.
    """
    def __init__(self, code_range, data_type, name):
        super().__init__(code_range)
        self.data_type = data_type
        self.name = name

    def __str__(self):
        return (
            f"(VariableDeclarationStmt {self.name} {self.data_type})"
        )


class AssignmentStmt_N(Stmt_N):
    """
    Base-class for all GeLB assignment statements.
    """
    def __init__(self, code_range, lhs, rhs):
        super().__init__(code_range)
        self.lhs = lhs
        self.rhs = rhs

    @abstractmethod
    def __str__(self):
        pass


class PaintNodesStmt_N(AssignmentStmt_N):
    """
    Represents a node-painting statement (@GeometryBlock).

    NOTE: - lhs = spatial_ranges
          - rhs = node_class
    """
    def __str__(self):
        return (
            f"(PaintNodesStmt"
            f" {self.lhs}"
            f" {self.rhs})"
        )


class VariableAssignmentStmt_N(AssignmentStmt_N):
    """
    Represents a variable-assignment statement.
    """
    def __str__(self):
        return (
            f"(VariableAssignmentStmt {self.lhs} {self.rhs})"
        )


class LatticeOutSelectionAssignmentStmt_N(AssignmentStmt_N):
    """
    Represents an assignment to a lattice-out (rectangular) selection.
    """
    def __str__(self):
        return (
            f"(LatticeOutSelectionAssignmentStmt {self.lhs} {self.rhs})"
        )
