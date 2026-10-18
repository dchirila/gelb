=================
Further Reading
=================

This chapter maps each tutorial chapter to the relevant sections
of three standard LBM textbooks, and provides a short bibliography
of the original papers cited throughout the tutorial.

Textbook cross-reference
=========================

.. list-table::
   :header-rows: 1
   :widths: 40 25 20

   * - Chapter
     - Krüger et al. (2017)
     - Mohamad (2019)
   * - :doc:`04_hello_world`
     - §3.2, §3.3.1–3.3.2
     - §2.2–2.3
   * - :doc:`05_1d_diffusion`
     - §3.2, §8.1, §8.3, §8.5.2.1
     - §5.1–5.5
   * - :doc:`07_lid_driven_cavity`
     - §5.3.3, §7.2
     - §8.3.1, §8.8.1
   * - :doc:`08_poiseuille_body_force`
     - §6 (Forces), §10 (MRT)
     - §8.3, §8.8.2, §10.1
   * - :doc:`09_rayleigh_benard`
     - §8.4.1–8.4.2
     - §9.6
   * - :doc:`10_karman_vortex`
     - §11.2.1 (staircase BB)
     - §8.8.3
   * - :doc:`11_shan_chen_multiphase`
     - §9.3
     - §11.1
   * - :doc:`12_beyond_lbm_gol`
     - — (not LBM)
     - —
   * - :doc:`13_salmon_ocean`
     - — (see Salmon 1999)
     - —

**Krüger et al.** = T. Krüger, H. Kusumaatmaja, A. Kuzmin,
O. Shardt, G. Silva & E. M. Viggen, *The Lattice Boltzmann Method:
Principles and Practice*, Springer, 2017.

**Mohamad** = A. A. Mohamad, *Lattice Boltzmann Method:
Fundamentals and Engineering Applications with Computer Codes*,
2nd ed., Springer, 2019.

A third useful reference for geoscience applications is:

**Sukop & Thorne** = M. C. Sukop & D. T. Thorne, *Lattice Boltzmann
Modeling: An Introduction for Geoscientists and Engineers*, Springer,
2006.  The tutorial's :doc:`10_karman_vortex` and
:doc:`11_shan_chen_multiphase` chapters are ported from Sukop's worked
examples.

Bibliography
=============

Original papers cited in the tutorial, in chronological order:

.. [ShanChen1993] X. Shan & H. Chen (1993).
   "Lattice Boltzmann model for simulating flows with multiple
   phases and components."
   *Physical Review E*, **47**, 1815–1819.
   — The pseudopotential multiphase model (:doc:`11_shan_chen_multiphase`).

.. [Ladd1994] A. J. C. Ladd (1994).
   "Numerical simulations of particulate suspensions via a
   discretized Boltzmann equation. Part 1. Theoretical foundation."
   *Journal of Fluid Mechanics*, **271**, 285–309.
   — Bounce-back boundary conditions (:doc:`07_lid_driven_cavity`,
   :doc:`08_poiseuille_body_force`).

.. [ZouHe1997] Q. Zou & X. He (1997).
   "On pressure and velocity boundary conditions for the lattice
   Boltzmann BGK model."
   *Physics of Fluids*, **9**, 1591–1598.
   — Velocity/pressure boundary conditions (:doc:`14_boundary_conditions_cookbook`).

.. [Salmon1999] R. Salmon (1999).
   "The lattice Boltzmann method as a basis for ocean circulation
   modeling."
   *Journal of Marine Research*, **57**, 503–535.
   — Reduced-gravity ocean model (:doc:`13_salmon_ocean`).

.. [dHumieres2002] D. d'Humières (2002).
   "Multiple-relaxation-time lattice Boltzmann models in three
   dimensions."
   *Philosophical Transactions of the Royal Society A*, **360**,
   437–451.
   — MRT collision operator (:doc:`08_poiseuille_body_force`,
   :doc:`09_rayleigh_benard`).

.. [Guo2002] Z. Guo, C. Zheng & B. Shi (2002).
   "Discrete lattice effects on the forcing term in the lattice
   Boltzmann method."
   *Physical Review E*, **65**, 046308.
   — Guo body force scheme (:doc:`08_poiseuille_body_force`,
   :doc:`13_salmon_ocean`).

.. [YoshidaNagaoka2010] H. Yoshida & M. Nagaoka (2010).
   "Multiple-relaxation-time lattice Boltzmann model for the
   convection and anisotropic diffusion equation."
   *Journal of Computational Physics*, **229**, 7774–7795.
   — Anti-bounce-back temperature BC (:doc:`09_rayleigh_benard`).
