#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_2068083195310390242);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_7749816067910704575);
void car_H_mod_fun(double *state, double *out_3649779414745672103);
void car_f_fun(double *state, double dt, double *out_1056771187663311893);
void car_F_fun(double *state, double dt, double *out_4304917159562798668);
void car_h_25(double *state, double *unused, double *out_1929353718823255889);
void car_H_25(double *state, double *unused, double *out_664622124210071326);
void car_h_24(double *state, double *unused, double *out_690260471304749903);
void car_H_24(double *state, double *unused, double *out_5938116407123083920);
void car_h_30(double *state, double *unused, double *out_5566803247077278239);
void car_H_30(double *state, double *unused, double *out_3182955082717319953);
void car_h_26(double *state, double *unused, double *out_6510313099978940674);
void car_H_26(double *state, double *unused, double *out_3076881194663984898);
void car_h_27(double *state, double *unused, double *out_1107432332621076796);
void car_H_27(double *state, double *unused, double *out_1639480134733593655);
void car_h_29(double *state, double *unused, double *out_7878267558971427732);
void car_H_29(double *state, double *unused, double *out_3352842861603144688);
void car_h_28(double *state, double *unused, double *out_504116447944599279);
void car_H_28(double *state, double *unused, double *out_1389212590037818437);
void car_h_31(double *state, double *unused, double *out_9056831590637407402);
void car_H_31(double *state, double *unused, double *out_3703089296897336374);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}