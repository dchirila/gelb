;;; gelb-mode.el --- major mode for editing GeLB files
;;; -*- coding: utf-8; lexical-binding: t; -*--

;; Copyright ©2021, Dragos Bogdan Chirila

;; Author: Dragos Bogdan Chirila (dchirila@gmail.com)
;; Version: 0.0.1
;; Created: 27 February, 2021
;; Homepage: gelb.site
;; License: You can redistribute this file and/or modify it under the terms of
;;          the GNU General Public License version 2.

;; NOTE This file is not part of GNU Emacs.

;; NOTE [Installation/Spacemacs]
;; (1) @=user-init=, add the following lines:
;;     ;; treat ".gelb" files as C++ (to get free auto-formatting with =clang-format=)
;;     (setq auto-mode-alist (cons '("\\.gelb$" . gelb-mode) auto-mode-alist))
;; (2) @=user-config=, add the following lines:
;;     (add-to-list 'load-path "~/path/to/this/file/parent/dir/")
;;     (load "gelb-mode")



;; define several categories of keywords

(setq gelb-keywords '(
                    "read_geometry_from_file"
                    "simulation_metadata"
                    "configuration"
                    "lattices_used"
                    "set_grid_size"
                    "gelb_version"
                    "node_classes"
                    "description"
                    "initializer"
                    "periodicity"
                    "node_class"
                    "properties"
                    "short_name"
                    "constants"
                    "category"
                    "df_alias"
                    "dynamics"
                    "function"
                    "geometry"
                    "lattices"
                    "dynamic"
                    "lattice"
                    "df_type"
                    "gauges"
                    "after"
                    "const"
                    "false"
                    "gauge"
                    "nodes"
                    "auto"
                    "name"
                    "none"
                    "size"
                    "true"
                    "zero"
                    "Sum"
                    "out"
                    "in"
                    "NX"
                    "NY"
                    "NZ"
                    "X"
                    "Y"
                    "Z"
                    "D"
                    "Q"
                    ))
(setq gelb-types '(
                                        ; =auto= type
                 "auto"
                                        ; =bool= type
                 "bool_const"
                 "bool" "Bool"
                                        ; =int= types
                 "int_const" "int8_const" "int16_const" "int32_const" "int64_const"
                 "int" "int8" "int16" "int32" "int64"
                                        ; =real= types
                 "real_const" "real16_const" "real32_const" "real64_const"
                 "real" "real16" "real32" "real64"
                                        ; array types
                 "array"
                 ))
(setq gelb-functions
      '(
        "DownStreamDF" "DownStreamDf" "downstreamdf"
        "UpStreamDF" "UpStreamDf" "upstreamdf"
        "OppositeDF" "OppositeDf" "oppositedf"
        "MultiplyElementWise" "multiplyelementwise"
        "DotProduct" "dotproduct"
        "Transpose" "transpose"
        "Inverse" "inverse"
        "Reduce" "reduce"
        "Random" "random"
        "Sqrt" "sqrt"
        "Nint" "nint"
        "Atan" "atan"
        "Sin" "sin"
        "Cos" "cos"
        ))

;; generate regex string for each category of keywords
(setq gelb-keywords-regexp (regexp-opt gelb-keywords 'words))
(setq gelb-type-regexp (regexp-opt gelb-types 'words))
(setq gelb-functions-regexp (regexp-opt gelb-functions 'words))

;; create the list for font-lock
;; (each category of keywords is given a particular face)
(setq gelb-font-lock-keywords
      `(
        (,gelb-type-regexp . font-lock-type-face)
        (,gelb-functions-regexp . font-lock-function-name-face)
        (,gelb-keywords-regexp . font-lock-keyword-face)
        ;; NOTE order above matters, because once colored that part won't change
        ;;      (so put longer words first)
        ))

;;;###autoload
(define-derived-mode gelb-mode c++-mode "GeLB mode"
  "Major mode for editing GeLB files"

  ;; code for syntax highlighting
  (setq font-lock-defaults '((gelb-font-lock-keywords))))

;; clear memory. no longer needed
(setq gelb-keywords nil)
(setq gelb-types nil)
(setq gelb-functions nil)

;; clear memory. no longer needed
(setq gelb-keywords-regexp nil)
(setq gelb-types-regexp nil)
(setq gelb-functions-regexp nil)

;; add the mode to the `features' list
(provide 'gelb-mode)
;;; =gelb-mode.el= ends here
