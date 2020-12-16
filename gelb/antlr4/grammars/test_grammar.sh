#!/bin/bash

echo '***WARNING*** This script is deprecated (use PyTest instead!)'

# help function
help() {
    # display help
    echo
    echo "Script to test rules for the GeLB description (GD) grammar"
    echo
    echo "Syntax:"
    echo "  test_grammar GRAMMAR_NAME START_RULE OUTPUT_TYPE GD_SNIPPET_FILE"
    echo
    echo "  where:"
    echo "       GRAMMAR_NAME (WITHOUT the .g4 extension)"
    echo "       START_RULE is any *parser* rule in the GD grammar"
    echo "                  (e.g. gd_version_stmt)"
    echo "       OUTPUT_TYPE is (tokens / tree / gui)"
    echo "       GD_SNIPPET_FILE is an (optional) file, containing a fragment"
    echo "                       of a GD program (or a complete GD program)"
}

# checking for CLI-args
## should pass *exactly* 4 CLI-args
if [ "$#" -ne 4 ]; then
    echo "<<<ERROR>>> Provide exactly 4 command-line arguments. Will abort..."
    help
    exit
fi

# fetch CLI-args
grammar_name=$1
start_rule=$2
gd_snippet_file=$3
output_type=$4

./cleanup.sh

#echo "grammar_name = ${grammar_name}"
#echo "start_rule = ${start_rule}"
#echo "gd_snippet_file = ${gd_snippet_file}"
#echo "output_type = ${output_type}"

# generate ANTLR4 lexer, parser, listener and/or visitor
java -Xmx500M -jar /usr/local/lib/antlr-4.8-complete.jar GD.g4
# compile ANTLR4-generated Java files
javac *.java
# run the TestRig tool
cat ${gd_snippet_file} | \
    java org.antlr.v4.gui.TestRig \
         ${grammar_name} \
         ${start_rule} \
         -${output_type}
