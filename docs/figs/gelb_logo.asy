settings.render=8;
settings.outformat='svg';
size(200);
import graph3;

texpreamble("\usepackage{fontspec}\setmainfont{JetBrains Mono NL Bold}");

int L=2, halfL = (L # 2);
currentprojection=perspective(0, -45, 180);
real r = 0.05;
surface site = scale3(r)*unitsphere;
real dist = 1.0;
real arrowLen=0.92;

pen gridLineColor = blue+opacity(0.2)+0.3pt;

void draw_df_arrow(triple s, real dist, triple dirVec) {
 frame f;
 pen dfArrowColor = gray(0.3)+opacity(0.5);

 draw(
        shift(s) * (O -- dist * arrowLen * dirVec),
        arrow=Arrow3(arrowheadpen=material(dfArrowColor, emissivepen=dfArrowColor)),
        p=dfArrowColor+1.1pt
 );
}


triple s;
/*********************
 * START :: EXE code *
 *********************/
// for(int i=-halfL; i<=halfL; ++i)
// {
//   for(int j=-halfL; j<=halfL; ++j)
//   {
//     int k = 0;
//     s=dist*(i,j,k);
//     draw(shift(s)*site, red+opacity(0.5));

//     if((i == 0) & (j == 0) & (k == 0)) {
//       draw_df_arrow(s, dist, O    );
//       draw_df_arrow(s, dist, +X   );
//       draw_df_arrow(s, dist,    +Y);
//       draw_df_arrow(s, dist, -X   );
//       draw_df_arrow(s, dist,    -Y);
//       draw_df_arrow(s, dist, +X +Y);
//       draw_df_arrow(s, dist, -X +Y);
//       draw_df_arrow(s, dist, -X -Y);
//       draw_df_arrow(s, dist, +X -Y);
//     }
//   }
// }

label("GeLB-lang", (0, 0), currentpen+fontsize(168pt)+rgb(255, 174, 13));
