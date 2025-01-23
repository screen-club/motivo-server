"""Test converter module."""

import pickle
import numpy as np
from scipy.spatial.transform import Rotation as R
import argparse

SKEL_JOINTS= [
    "Pelvis",
    "L_Hip",
    "R_Hip",
    "Torso",
    "L_Knee",
    "R_Knee",
    "Spine",
    "L_Ankle",
    "R_Ankle",
    "Chest",
    "L_Toe",
    "R_Toe",
    "Neck",
    "L_Thorax",
    "R_Thorax",
    "Head",
    "L_Shoulder",
    "R_Shoulder",
    "L_Elbow",
    "R_Elbow",
    "L_Wrist",
    "R_Wrist",
    "L_Hand",
    "R_Hand",
]


def _get_euler_from_smpl_poses(smpl_poses, idx) -> np.ndarray:
    rotvec = smpl_poses[:, idx*3:idx*3+3]
    euler = []
    for _f in range(rotvec.shape[0]):
        rot = R.from_rotvec(
            [rotvec[_f, 0], rotvec[_f, 1], rotvec[_f, 2]],
        )
        _euler = rot.as_euler("xyz", degrees=True)
        euler.append([_euler[0], _euler[1], _euler[2]])
    return np.vstack(euler)

def main_test(pkl_path: str) -> None:
    print(f"\nLoading pickle file from: {pkl_path}")
    
    with open(pkl_path, "rb") as pkl_file:
        smpl_data = pickle.load(pkl_file)
    
    # Print full contents of the pickle file
    print("\nComplete pickle file contents:")
    for key, value in smpl_data.items():
        print(f"\nKey: {key}")
        print(f"Type: {type(value)}")
        if isinstance(value, np.ndarray):
            print(f"Shape: {value.shape}")
            print(f"Data: {value}")
        else:
            print(f"Value: {value}")

    axes_order = None
    pose_offset = None
    bones_remap = None

    # 1. Write smpl_poses
    smpl_poses = smpl_data["smpl_poses"]
    for idx, name in enumerate(SKEL_JOINTS):
        order = "XYZ"
        if axes_order and name in axes_order:
            order = axes_order[name]
        offset = [0, 0, 0]
        if pose_offset and name in pose_offset:
            offset = pose_offset[name]
        if bones_remap and name in bones_remap:
            name = bones_remap[name]
        euler = _get_euler_from_smpl_poses(smpl_poses, idx)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert SMPL poses from pickle file.')
    parser.add_argument('--input', type=str, required=True,
                      help='Path to the input SMPL pickle file')
    
    args = parser.parse_args()
    main_test(args.input)