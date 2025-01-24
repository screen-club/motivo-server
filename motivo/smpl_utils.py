from scipy.spatial.transform import Rotation as sRot
import numpy as np

# Updated to match the exact order
SMPL_BONE_ORDER_NAMES = [
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

SMPLH_BONE_ORDER_NAMES = [
    # Add SMPLH bone names if needed
]

def get_body_qposaddr(model):
    """Get the position address mapping for each body in the model"""
    body_qposaddr = dict()
    
    # Handle both old and new MuJoCo API
    try:
        # New MuJoCo API
        for i in range(model.nbody):
            body_name = model.body(i).name
            start_joint = model.body_jntadr[i]
            if start_joint < 0:
                continue
            end_joint = start_joint + model.body_jntnum[i]
            start_qposaddr = model.jnt_qposadr[start_joint]
            if end_joint < len(model.jnt_qposadr):
                end_qposaddr = model.jnt_qposadr[end_joint]
            else:
                end_qposaddr = model.nq
            body_qposaddr[body_name] = (start_qposaddr, end_qposaddr)
    except AttributeError:
        # Old MuJoCo API
        for i, body_name in enumerate(model.body_names):
            start_joint = model.body_jntadr[i]
            if start_joint < 0:
                continue
            end_joint = start_joint + model.body_jntnum[i]
            start_qposaddr = model.jnt_qposadr[start_joint]
            if end_joint < len(model.jnt_qposadr):
                end_qposaddr = model.jnt_qposadr[end_joint]
            else:
                end_qposaddr = model.nq
            body_qposaddr[body_name] = (start_qposaddr, end_qposaddr)
            
    return body_qposaddr

def qpos_to_smpl(qpos, mj_model, smpl_model="smpl"):
    body_qposaddr = get_body_qposaddr(mj_model)
    
    # Convert qpos to numpy if it's a torch tensor
    if hasattr(qpos, 'detach'):
        qpos = qpos.detach().cpu().numpy()
    
    # Ensure qpos is 2D
    if len(qpos.shape) == 1:
        qpos = qpos.reshape(1, -1)
    
    batch_size = qpos.shape[0]
    trans = qpos[:, :3] - mj_model.body_pos[1]
    smpl_bones_to_use = (SMPL_BONE_ORDER_NAMES if smpl_model == "smpl" else SMPLH_BONE_ORDER_NAMES)
    pose = np.zeros([batch_size, len(smpl_bones_to_use), 3])
    
    for ind1, bone_name in enumerate(smpl_bones_to_use):
        ind2 = body_qposaddr[bone_name]
       # print(f"ind1: {ind1}, Bone: {bone_name}, Indices: {ind2}")
        if ind1 == 0:
            quat = qpos[:, 3:7]
            pose[:, ind1, :] = sRot.from_quat(quat[:, [1, 2, 3, 0]]).as_rotvec()
        else:
            pose[:, ind1, :] = sRot.from_euler("XYZ", qpos[:, ind2[0]:ind2[1]]).as_rotvec()

    return pose, trans 