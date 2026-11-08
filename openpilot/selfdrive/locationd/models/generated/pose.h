#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_7607340466644126338);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_6802001497691266902);
void pose_H_mod_fun(double *state, double *out_8360352250640609347);
void pose_f_fun(double *state, double dt, double *out_1729733863847722677);
void pose_F_fun(double *state, double dt, double *out_6589700326730162728);
void pose_h_4(double *state, double *unused, double *out_2977686091862971139);
void pose_H_4(double *state, double *unused, double *out_6885981921967472245);
void pose_h_10(double *state, double *unused, double *out_2063640600098317601);
void pose_H_10(double *state, double *unused, double *out_5665626610612883032);
void pose_h_13(double *state, double *unused, double *out_7607718264744722863);
void pose_H_13(double *state, double *unused, double *out_3950130943425378442);
void pose_h_14(double *state, double *unused, double *out_4555210887505306851);
void pose_H_14(double *state, double *unused, double *out_3803193489672099949);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}