gd_version = 1;

configuration {         //
  simulation_metadata { //
    short_name = "game_of_life_random_ICs";
    description = "";
  }
  constants { //
    const int N_NEAREST = 8;
  }
}

lattices { //
  lattice f(D = 2, Q = 1, df_type = bool, size = {40, 40},
            periodicity = {true, true});
}

node_classes {
  node_class BULK(initializer = RandomLife, dynamics = LifeEvolve,
                  gauges = CellStatus);
}

initializer RandomLife { //
  f.out [x, y |:] = Random();
}

dynamic LifeEvolve {
  const array<bool, {N_NEAREST}> genesis = //
      {false, false, false,                //
       true,                               // genesis for 3 neighbors
       false, false, false, false, false};
  const array<bool, {N_NEAREST}> deathOrSurvival = //
      {false, false,                               // death by loneliness
       true,  true,                                // survival
       false, false, false, false, false};         // death by overcrowding

  int neighborSum;

  neighborSum = int(f.in[x - 1, y - 1 | 0]) + int(f.in[x - 1, y | 0]) +
                int(f.in[x - 1, y + 1 | 0]) + int(f.in[x, y - 1 | 0]) +
                int(f.in[x, y + 1 | 0]) + int(f.in[x + 1, y - 1 | 0]) +
                int(f.in[x + 1, y | 0]) + int(f.in[x + 1, y + 1 | 0]);

  f.out[x, y | 0] = (f.in[x, y | 0] && deathOrSurvival[neighborSum]) ||
                    ((!f.in[x, y | 0]) && genesis[neighborSum]);
}

gauge CellStatus(out(bool status)) { //
  status = f.in[x, y | 0];
}

geometry { //
  nodes[:, :] = BULK;
}
