import torch
from humenv import make_humenv
from gymnasium.wrappers import FlattenObservation, TransformObservation
from metamotivo.fb_cpr.huggingface import FBcprModel
from huggingface_hub import hf_hub_download
import h5py
import numpy as np
import cv2  # Option 1: Using OpenCV
from PIL import Image  # Option 2: Using PIL
from pathlib import Path
from humenv.env import make_from_name
from humenv import rewards as humenv_rewards
from metamotivo.wrappers.humenvbench import relabel
import time

def setup_environment(device="cpu"):
    # Create and configure the environment
    env, _ = make_humenv(
        num_envs=1,
        wrappers=[
            FlattenObservation,
            lambda env: TransformObservation(
                env, 
                lambda obs: torch.tensor(obs.reshape(1, -1), 
                                      dtype=torch.float32, 
                                      device=device),
                env.observation_space
            ),
        ],
        state_init="Default",
    )
    return env

def run_simulation(model, env, num_steps=100, record=False, render_freq=1):
    """
    Run simulation with options for more frames or real-time rendering
    Args:
        model: The model to run
        env: The environment
        num_steps: Number of simulation steps
        record: Whether to record frames
        render_freq: Render every N steps (1 = every frame, 2 = every other frame, etc.)
    """
    z = model.sample_z(1)
    observation, _ = env.reset()
    
    # Initialize frames list if recording
    frames = [env.render()] if record else []
    
    # Run simulation loop
    for step in range(num_steps):
        action = model.act(observation, z, mean=True)
        observation, reward, terminated, truncated, info = env.step(
            action.cpu().numpy().ravel()
        )
        
        # Record frame if needed (based on frequency)
        if record and step % render_freq == 0:
            frame = env.render()
            frames.append(frame)
            
            # Option 1: Display using OpenCV
            cv2.imshow('Simulation', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            cv2.waitKey(1)  # 1ms delay
            
            # Option 2: Display using PIL
            # Image.fromarray(frame).show()
            
            time.sleep(1/30)  # 30 FPS
        
        if terminated or truncated:
            observation, _ = env.reset()
    
    if record:
        cv2.destroyAllWindows()  # Clean up OpenCV windows
        return frames
    return None

def download_buffer(model_name="metamotivo-S-1", dataset="buffer_inference_500000.hdf5"):
    """Download and create a buffer for inference"""
    local_dir = f"{model_name}-datasets"
    buffer_path = hf_hub_download(
        repo_id=f"facebook/{model_name}",
        filename=f"data/{dataset}",
        repo_type="model",
        local_dir=local_dir,
    )
    
    # Load buffer data directly as a dictionary
    with h5py.File(buffer_path, "r") as hf:
        print("Available buffer keys:", list(hf.keys()))  # Debug print
        data = {k: np.array(v) for k, v in hf.items()}
    
    return data

def demonstrate_model_functions(model, observation, z):
    """Demonstrate different model functions"""
    print("\nDemonstrating model functions:")
    
    # Get action from actor
    action = model.act(observation, z, mean=True)
    print(f"Action shape: {action.shape}")
    
    # Forward mapping
    next_obs_pred = model.forward_map(observation, z, action)
    print(f"Forward prediction shape: {next_obs_pred.shape}")
    
    # Backward mapping
    z_pred = model.backward_map(observation)
    print(f"Backward mapping shape: {z_pred.shape}")
    
    # Critic value
    value = model.critic(observation, z, action)
    print(f"Critic value shape: {value.shape}")
    
    # Discriminator output
    disc_output = model.discriminator(observation, z)
    print(f"Discriminator output shape: {disc_output.shape}")

def run_inference_examples(model, env, buffer_data):
    """Demonstrate different inference methods"""
    print("\nDemonstrating inference methods:")
    
    # Get random indices for sampling
    idx = np.random.randint(0, len(buffer_data['observation']), 100)
    
    # Sample some data from buffer using correct keys
    obs = torch.tensor(buffer_data['observation'][idx], dtype=torch.float32)
    next_obs = torch.tensor(buffer_data['next_observation'][idx], dtype=torch.float32)
    
    # Since we don't have direct reward data, we can compute a simple reward
    # This is just an example - you might want to adjust the reward calculation
    rewards = torch.zeros(len(idx), dtype=torch.float32)  # placeholder rewards
    
    # Reward inference
    z_reward = model.reward_inference(next_obs, rewards)
    print(f"Reward inference z shape: {z_reward.shape}")
    
    # Weighted reward inference
    z_reward_weighted = model.reward_wr_inference(next_obs, rewards)
    print(f"Weighted reward inference z shape: {z_reward_weighted.shape}")
    
    # Goal inference
    z_goal = model.goal_inference(next_obs)
    print(f"Goal inference z shape: {z_goal.shape}")
    
    # Tracking inference
    z_tracking = model.tracking_inference(next_obs)
    print(f"Tracking inference z shape: {z_tracking.shape}")

def save_video(frames, filename, fps=30):
    """Save frames as a video file"""
    # Ensure output directory exists
    output_dir = Path("output_videos")
    output_dir.mkdir(exist_ok=True)
    
    # Full path for the video
    video_path = output_dir / filename
    
    # Using OpenCV to write video instead of mediapy
    if frames:
        height, width, layers = frames[0].shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
        
        for frame in frames:
            # Convert from RGB to BGR for OpenCV
            out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        
        out.release()
        print(f"Video saved to: {video_path}")

def demonstrate_examples(model, env, buffer_data):
    """Demonstrate different examples with video recording"""
    print("\nDemonstrating different examples:")
    
    # Example with more frames (300 instead of 30)
    print("Running random policy example...")
    frames = run_simulation(model, env, num_steps=300, record=True)
    save_video(frames, "random_policy.mp4", fps=30)
    
    # Example with real-time rendering (every 2nd frame)
    print("\nRunning goal-directed example...")
    qpos_dim = env.unwrapped.model.nq
    qvel_dim = env.unwrapped.model.nv
    goal_qpos = np.zeros(qpos_dim)
    env.unwrapped.set_physics(qpos=goal_qpos, qvel=np.zeros(qvel_dim))
    goal_obs = torch.tensor(
        env.unwrapped.get_obs()["proprio"].reshape(1,-1), 
        device=model.cfg.device, 
        dtype=torch.float32
    )
    z = model.goal_inference(next_obs=goal_obs)
    frames = run_simulation(model, env, num_steps=300, record=True, render_freq=1)
    save_video(frames, "goal_directed.mp4", fps=30)
    
    # 3. Reward-based example
    print("\nRunning reward-based example...")
    batch_size = 100_000
    idx = np.random.randint(0, len(buffer_data['observation']), batch_size)
    
    batch = {
        'next_qpos': buffer_data['next_qpos'][idx],
        'next_qvel': buffer_data['next_qvel'][idx],
        'action': buffer_data['action'][idx],
        'next_observation': buffer_data['next_observation'][idx]
    }
    
    reward_fn = make_from_name("move-ego-0-2")
    
    rewards = relabel(
        env,
        qpos=batch['next_qpos'],
        qvel=batch['next_qvel'],
        action=batch['action'],
        reward_fn=reward_fn,
        max_workers=8
    )
    
    z = model.reward_wr_inference(
        next_obs=torch.tensor(batch['next_observation'], device=model.cfg.device, dtype=torch.float32),
        reward=torch.tensor(rewards, device=model.cfg.device, dtype=torch.float32)
    )
    frames = run_simulation(model, env, num_steps=300, record=True, render_freq=1)
    save_video(frames, "reward_based.mp4", fps=30)

def main():
    # Setup device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    # Load model and environment
    model_name = "metamotivo-S-1"
    model = FBcprModel.from_pretrained(f"facebook/{model_name}")
    model.to(device)
    env = setup_environment(device)
    
    # Download and setup buffer
    buffer_data = download_buffer(model_name)
    
    # Get initial observation
    observation, _ = env.reset()
    
    # Sample context vector
    z = model.sample_z(1)
    
    # Demonstrate different functionalities
    demonstrate_model_functions(model, observation, z)
    run_inference_examples(model, env, buffer_data)
    
    # Replace the separate demonstration calls with the new combined one
    demonstrate_examples(model, env, buffer_data)
    
    print("\nAll examples completed!")

if __name__ == "__main__":
    main()
