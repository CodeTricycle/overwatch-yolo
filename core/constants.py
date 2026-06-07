FIRE_MODE = {
    "按下": "press",
    "切换": "toggle",
}

TRIGGER_MODE_MAP = FIRE_MODE

V_ON = "start_video"
V_OFF = "stop_video"
MDL_SWAP = "change_model"
CLS_SET = "change_class"
CONF_SET = "change_conf"
RANGE_SET = "detection_radius_change"

DET_ON = "YOLO_start"
DET_OFF = "YOLO_stop"
DISP_ON = "display_on"
DISP_OFF = "display_off"

AIM_TOGGLE = "aimbot_switch_change"
SPD_X = "h_sensitivity_change"
SPD_Y = "v_sensitivity_change"
OFF_X = "h_compensation_change"
OFF_Y = "v_compensation_change"
BIND_KEY = "lock_key_change"
FIRE_MODE_SET = "trigger_mode_change"
SCR_PX360 = "yaw_pixel_count"
SCR_PXH = "pitch_pixel_count"

KF_ON = "kalman_filter_enabled"
KF_PN = "kalman_process_noise"
KF_MN = "kalman_measurement_noise"
KF_COAST = "kalman_coast_max_frames"
KF_REINIT = "kalman_reinit_distance_threshold"

HM_ON = "humanize_enabled"
HM_MAX = "humanize_max_speed"
HM_REACT = "humanize_reaction_dist"
HM_ALPHA = "humanize_alpha"
HM_JITTER = "humanize_jitter"

EVT_READY = "loading_complete"
EVT_LOG = "log_output_main"
EVT_ERR = "error_log"
EVT_FATAL = "red_error_log"
EVT_CAP_LOG = "video_signal_acquisition_log"
EVT_PROC_LOG = "video_processing_log"
EVT_UI_LOG = "UI_process_log"
