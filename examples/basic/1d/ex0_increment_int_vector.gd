lattices { //
  lattice f(D = 1, Q = 1, df_type = int, size = {32}, periodicity = {false});
}

initializer SetToZero { //
  f.out[x | 0] = 0;
}

dynamic IncrementDFs { //
  f.out[x | 0] = f.in[x | 0] + 1;
}

gauge CurrentState[out(int state)] { //
  state = f.in[x | 0];
}

node_classes { //
  node_class BULK(SetToZero, IncrementDFs, CurrentState);
}

geometry { //
  nodes[:] = BULK;
}
