#!/usr/bin/env python3

import os
import gelb.utils.config
from gelb.utils.output_to_terminal import error_with_hint_to_term
from gelb.utils.error_utils import (
    feedback_on_slack_hint,
    learning_gelb_hint,
    show_error_in_src
)

class GeLBException(Exception):
    """Base-class for all GeLB exceptins."""
    def __init__(self, error, hint):
        # we rely on the custom fields {error,hint} because we want to do our
        # own printing (instead of relying on the Python default)
        self.error = error
        self.hint = hint

    def __str__(self):
        error_with_hint_to_term(self.error, self.hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            os._exit(1)  # really abort


class GeLBExInvalidGrammarRule(GeLBException):
    """
    GeLB exception, for attempts to use a parser rule which is not part of
    the grammar.
    """
    def __init__(self, rule_name):
        error = f"(internal) can't find rule \"{rule_name}\" @GeLBParser"
        hint = (
            f"If you are a GeLB developer, please check whether rule"
            f" \"{rule_name}\" is part of the grammar (look @\"GeLB.g4\""
            f" file). " + feedback_on_slack_hint
        )
        super().__init__(error, hint)


class GeLBExMissingCSTVisitationMethod(GeLBException):
    """
    GeLB exception, for attempting to invoke a CST visitation method which
    has not been defined.
    """
    def __init__(self, rule_name):
        visitation_method_name = f"visit{rule_name.capitalize()}"
        error = (
            f"(internal) can't find method \"{visitation_method_name}\""
            f"@ASTBuilderVisitor"
        )
        hint = (
            f"If you are a GeLB developer, please check whether rule"
            f" \"{rule_name}\" is part of the grammar (look @\"GeLB.g4\""
            f" file). Also, check that the ANTLR4 Java tool actually"
            f" generated a method named \"{visitation_method_name}\" (look"
            f" @\"GeLBVisitor.py\"). " + feedback_on_slack_hint

        )
        super().__init__(error, hint)


class GeLBExMissingASTVisitationMethod(GeLBException):
    """
    GeLB exception, for attempting to invoke an AST visitation method which
    has not been defined.
    """
    def __init__(self, visitor_subclass_name, visitation_method_name):
        error = (
            f"(internal) can't find method \"{visitation_method_name}\""
            f"@{visitor_subclass_name}"
        )
        hint = (
            f"If you are a GeLB developer (maybe implementing a new compiler "
            f"pass) please check whether you actually defined the appropriate "
            f"method in your ASTBaseVisitor subclass"
            f" (i.e. \"{visitor_subclass_name}\"). " + feedback_on_slack_hint

        )
        super().__init__(error, hint)


class GeLBExSyntaxError(GeLBException):
    """
    GeLB exception, for catching syntax errors raised by the generated parser.
    """
    def __init__(self, line, column, error, hint):
        self.line = line
        self.column = column
        super().__init__(error, hint)
        print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        show_error_in_src(self.line, self.column, self.error, self.hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            os._exit(1)  # really abort


class GeLBExInvalidNoOfBlockOccurrences(GeLBException):
    """
    GeLB exception, for signaling an invalid number of high-level block
    occurrences.
    """
    def __init__(self, block_name, min_no, max_no, line, column):
        self.line = line
        self.column = column
        if (max_no == 1):
            error = (
                f"We see that you declare the \"{block_name}\" more than once."
            )
            if (min_no == 1):
                hint = (
                    f"[Hint] We expect exactly one instance of"
                    f" \"{block_name}\". " + learning_gelb_hint
                )
            elif (min_no == 0):
                hint = (
                    f"[Hint] We expect at most one instance of"
                    f" \"{block_name}\" (or none -- it is optonal, because"
                    f" not all simulations need it). " + learning_gelb_hint
                )
        else:  # max_no > 1
            raise NotImplementedError()
        super().__init__(error, hint)
        print(self)

    def __str__(self):
        """Override base-class's __str__, because we want to print the code"""
        show_error_in_src(self.line, self.column, self.error, self.hint)
        if gelb.utils.config.GELB_PRODUCTION_MODE:
            os._exit(1)  # really abort


class GeLBExIncorrectInputFileExtension(GeLBException):
    """
    GeLB exception, for signaling an incorrect input-file extension.
    """
    def __init__(self, input_file_name):
        error = (
            f"[Problem] We notice that your input file \"{input_file_name}\""
            f" does not have the \".gelb\" extension."
        )
        hint = (
            f"[Hint] Please speficy a file that ends in \".gelb\""
        )
        super().__init__(error, hint)


class GeLBExCouldNotFindInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file could not be found.
    """
    def __init__(self, input_file_name, suggest_files):
        error = (
            f"[Problem] We could not find the input file \"{input_file_name}\"."
        )
        hint = (
            f"[Hint] Please specify a file that exists."
        )
        if suggest_files:
            hint += (
                f" Maybe you meant one of the following files?"
                f" {suggest_files}"
            )
        super().__init__(error, hint)


class GeLBExCouldNotReadInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file could not be read (
    presumably due to file-permission errors).
    """
    def __init__(self, input_file_name):
        error = (
            f"[Problem] We could not read the input file \"{input_file_name}\"."
        )
        hint = (
            f"[Hint] Change permissions for file \"{input_file_name}\","
            f" to allow gelbc to read it."
        )
        super().__init__(error, hint)


class GeLBExEmptyInputFile(GeLBException):
    """
    GeLB exception, for signaling that the input file does not contain any
    code (could be empty, or just whitespace).
    """
    def __init__(self, input_file_name=None):
        error = (
            f"[Problem] The input file \"{input_file_name}\" does not"
            f" contain any GeLB code."
        )
        hint = (
            f"[Hint] {learning_gelb_hint}"
        )
        super().__init__(error, hint)
