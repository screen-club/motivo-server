import os
import cv2
import numpy as np
import json
from datetime import datetime

def save_frame_data(frame, qpos, qvel, smpl_data=None):
    """
    Save current frame image and state data
    
    Args:
        frame: RGB image frame from the simulation
        qpos: Position state data
        qvel: Velocity state data
        smpl_data: Optional SMPL parameters dictionary containing poses, betas, and trans
    """
    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("captured_frames", timestamp)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save image
    image_path = os.path.join(output_dir, "frame.png")
    cv2.imwrite(image_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    
    # Save state data as NPZ
    data = {
        'qpos': qpos,
        'qvel': qvel,
        'timestamp': timestamp
    }
    if smpl_data:
        data.update(smpl_data)
    
    data_path = os.path.join(output_dir, "state_data.npz")
    np.savez(data_path, **data)
    
    # Save state data as JSON
    json_data = {
        'qpos': qpos.tolist(),
        'qvel': qvel.tolist(),
        'timestamp': timestamp
    }
    if smpl_data:
        json_data.update({k: v.tolist() if isinstance(v, np.ndarray) else v 
                         for k, v in smpl_data.items()})
    
    json_path = os.path.join(output_dir, "state_data.json")
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"Saved frame and state data to: {output_dir}") 