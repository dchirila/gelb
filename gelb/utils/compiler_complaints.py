#!/usr/bin/env python3

from gelb.utils.output_to_terminal import fatal_error_with_hint_to_term


def complain_about_missing_visitor_method(rule, visitor_method_name):
    fatal_error_with_hint_to_term(
        f"(internal) can't find method \"{visitor_method_name}\""
        f"@ASTBuilderVisitor",
        # hint
        f"If you are a GeLB developer, please check whether rule"
        f" \"{rule}\" is part of the grammar (look @\"GeLB.g4\""
        f" file). Also, check that the ANTLR4 Java tool actually"
        f" generated a method named \"{visitor_method_name}\" (look"
        f" @\"GeLBVisitor.py\").\n\n"
        f"If you are a GeLB user, please report this error on our"
        f" Slack #feedback channel (https://gelb-devs.slack.com)."
    )


def complain_about_invalid_grammar_rule(rule):
    fatal_error_with_hint_to_term(
        f"(internal) can't find rule \"{rule}\" @GeLBParser",
        # hint
        f"If you are a GeLB developer, please check whether rule"
        f" \"{rule}\" is part of the grammar (look @\"GeLB.g4\""
        f" file).\n\n"
        f"If you are a GeLB user, please report this error on our"
        f" Slack #feedback channel (https://gelb-devs.slack.com)."
    )
