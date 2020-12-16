;;; gd-mode.el --- major mode for editing GD (Gelb Description) files
;;; -*- coding: utf-8; lexical-binding: t; -*--

;; Copyright ©2020, Dragos Bogdan Chirila

;; Author: Dragos Bogdan Chirila (dchirila@gmail.com)
;; Version: 0.0.1
;; Created: 1 December 2020
;; Homepage: gelb.site
;; License: You can redistribute this file and/or modify it under the terms of
;;          the GNU General Public License version 2.

;; NOTE This file is not part of GNU Emacs.

;; NOTE [Installation/Spacemacs] @=user-config=, add a line such as:
;; (add-to-list 'load-path "~/path/to/this/file/parent/dir/")


;; define several categories of keywords

(setq gd-keywords '(
                    "read_geometry_from_file"
                    "simulation_metadata"
                    "node_categories"
                    "set_grid_size"
                    "lattices_used"
                    "configuration"
                    "gelb_version"
                    "initializer"
                    "description"
                    "short_name"
                    "properties"
                    "node_range"
                    "constants"
                    "geometry"
                    "periodic"
                    "function"
                    "lattices"
                    "df_alias"
                    "category"
                    "dynamics"
                    "dynamic"
                    "lattice"
                    "df_type"
                    "false"
                    "gauges"
        "const"
                    "after"
                    "gauge"
                    "true"
                    "zero"
                    "none"
                    "node"
                    "name"
                    "auto"
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
(setq gd-types '(
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
(setq gd-functions
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
(setq gd-keywords-regexp (regexp-opt gd-keywords 'words))
(setq gd-type-regexp (regexp-opt gd-types 'words))
(setq gd-functions-regexp (regexp-opt gd-functions 'words))

;; create the list for font-lock
;; (each category of keywords is given a particular face)
(setq gd-font-lock-keywords
      `(
        (,gd-type-regexp . font-lock-type-face)
        (,gd-functions-regexp . font-lock-function-name-face)
        (,gd-keywords-regexp . font-lock-keyword-face)
        ;; NOTE order above matters, because once colored that part won't change
        ;;      (so put longer words first)
        ))

;;;###autoload
(define-derived-mode gd-mode c++-mode "GD mode"
  "Major mode for editing GD (Gelb Description) language"

  ;; code for syntax highlighting
  (setq font-lock-defaults '((gd-font-lock-keywords))))

;; clear memory. no longer needed
(setq gd-keywords nil)
(setq gd-types nil)
(setq gd-functions nil)

;; clear memory. no longer needed
(setq gd-keywords-regexp nil)
(setq gd-types-regexp nil)
(setq gd-functions-regexp nil)

;; add the mode to the `features' list
(provide 'gd-mode)
;;; =gd-mode.el= ends here
