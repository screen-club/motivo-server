import h5py
import numpy as np
from huggingface_hub import hf_hub_download

def download_buffer(model_name="metamotivo-M-1", dataset="buffer_inference_500000.hdf5"):
    """Download and create a buffer for inference"""
    from core.config import config
    import os
    
    # Use a datasets directory within the storage directory
    datasets_dir = os.path.join(config.storage_dir, "datasets")
    os.makedirs(datasets_dir, exist_ok=True)
    
    local_dir = os.path.join(datasets_dir, f"{model_name}-datasets")
    buffer_path = hf_hub_download(
        repo_id=f"facebook/{model_name}",
        filename=f"data/{dataset}",
        repo_type="model",
        local_dir=local_dir,
    )
    
    with h5py.File(buffer_path, "r") as hf:
        data = {k: np.array(v) for k, v in hf.items()}
    return data 